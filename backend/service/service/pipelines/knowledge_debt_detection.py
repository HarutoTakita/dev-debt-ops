"""knowledge-debt-detection pipeline (issue 030).

Detects ``ai_generated`` / ``author_left`` / ``no_review`` knowledge debts per file using
``GitHubGitClient`` (commit history / commit→PR / reviews) + a Gemini AI-generation estimate,
joins issue 029's ``file_kc`` for ``knowledge_coverage`` and ``assigned_developers``
(coverage / certified_via), and upserts ``knowledge_debts`` / ``assigned_developers`` under an
``analysis_run``. ``shared.worker.run_task`` owns the Job lifecycle + ``result_data``.

Idempotent across at-least-once redelivery: the run is keyed by ``job_id``; ``knowledge_debts``
upsert on ``(run_id, file_path, reason)`` and ``assigned_developers`` on
``(debt_kind, debt_id, github_handle)``.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.services import code_analysis, gemini_stack_service, knowledge_analysis
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import AnalysisRun, AssignedDeveloper, FileKc, KnowledgeDebt
from shared.pipelines.context import PipelineContext
from shared.schemas.knowledge_debt_detection import KnowledgeDebtDetectionRequest, KnowledgeDebtDetectionResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)

_MAX_FILES = 50
_MAX_SNIPPET_LINES = 20


async def _mint_installation_token(github: GitHubRef) -> str:
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


def _is_source(path: str) -> bool:
    return path.lower().endswith(
        (".py", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
    ) and not code_analysis.is_vendored_path(path)


def _age_days(authored_at: str, *, now: datetime) -> int:
    """Age in days of an ISO-8601 timestamp; 0 if unparseable."""
    if not authored_at:
        return 0
    try:
        dt = datetime.fromisoformat(authored_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, (now - dt).days)


async def _kc_by_file(session: AsyncSession, project_id: uuid.UUID) -> dict[str, dict]:
    """Latest kc_analysis run's file_kc for the project, keyed by file_path.

    Returns ``{path: {"coverage": <aggregate kc>, "devs": [(handle, kc, certified_via), ...]}}``.
    Empty when no KC run exists yet (029 not run) — callers fall back to provisional 0.0.
    """
    kc_run = (
        await session.execute(
            select(AnalysisRun)
            .where(
                AnalysisRun.project_id == project_id,  # ty: ignore[invalid-argument-type]
                AnalysisRun.kind == JobType.KC_ANALYSIS.value,  # ty: ignore[invalid-argument-type]
            )
            .order_by(col(AnalysisRun.created_at).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if kc_run is None:
        return {}

    rows = (
        (
            await session.execute(select(FileKc).where(FileKc.run_id == kc_run.id))  # ty: ignore[invalid-argument-type]
        )
        .scalars()
        .all()
    )
    by_file: dict[str, dict] = {}
    for row in rows:
        entry = by_file.setdefault(row.file_path, {"coverage": 0.0, "devs": []})
        if row.github_handle is None and row.dev_id is None:
            entry["coverage"] = row.kc  # aggregate row
        elif row.github_handle is not None:
            entry["devs"].append((row.github_handle, row.kc, row.certified_via))
    return by_file


async def _get_or_create_run(
    session: AsyncSession, *, job_id: uuid.UUID, project_id: uuid.UUID, commit_sha: str, branch: str
) -> AnalysisRun:
    existing = (
        await session.execute(
            select(AnalysisRun).where(
                col(AnalysisRun.job_id) == job_id,
                col(AnalysisRun.kind) == JobType.KNOWLEDGE_DEBT_DETECTION.value,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    run = AnalysisRun(
        project_id=project_id,
        commit_sha=commit_sha,
        branch=branch,
        kind=JobType.KNOWLEDGE_DEBT_DETECTION.value,
        job_id=job_id,
        status=JobStatus.PROCESSING,
    )
    session.add(run)
    await session.flush()
    return run


async def _upsert_knowledge_debt(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    repo: str,
    file_path: str,
    reason: str,
    score: float,
    notes: str,
    snippet: str,
    ai_prob: float,
    coverage: float,
    repay: float,
) -> uuid.UUID:
    now = datetime.now(UTC)
    severity = code_analysis.quantize_severity(score)
    common = {
        "severity": severity,
        "status": "open",
        "detected_at": now,
        "code_snippet": snippet,
        "code_debt_score": score,
        "knowledge_coverage": coverage,
        "ai_generation_prob": ai_prob,
        "estimated_repay_hours": repay,
        "detection_notes": notes,
        "metrics": {},
    }
    stmt = pg_insert(KnowledgeDebt).values(
        id=uuid.uuid4(), project_id=project_id, run_id=run_id, file_path=file_path, repo=repo, reason=reason, **common
    )
    stmt = stmt.on_conflict_do_update(constraint="uq_knowledge_debts_run_file_reason", set_=common)
    await session.execute(stmt)
    # Re-read the (possibly pre-existing) row by its unique key for assigned_developers FK-by-value.
    row = (
        await session.execute(
            select(KnowledgeDebt).where(
                KnowledgeDebt.run_id == run_id,  # ty: ignore[invalid-argument-type]
                KnowledgeDebt.file_path == file_path,  # ty: ignore[invalid-argument-type]
                KnowledgeDebt.reason == reason,  # ty: ignore[invalid-argument-type]
            )
        )
    ).scalar_one()
    return row.id


async def _upsert_assigned(
    session: AsyncSession, *, debt_id: uuid.UUID, handle: str, coverage: float, certified_via: str | None
) -> None:
    stmt = pg_insert(AssignedDeveloper).values(
        id=uuid.uuid4(),
        debt_kind="knowledge",
        debt_id=debt_id,
        github_handle=handle,
        coverage=coverage,
        certified_via=certified_via,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_assigned_developers_debt_handle",
        set_={"coverage": coverage, "certified_via": certified_via},
    )
    await session.execute(stmt)


def _snippet(content: str) -> str:
    return "\n".join(content.splitlines()[:_MAX_SNIPPET_LINES])


async def process(request: KnowledgeDebtDetectionRequest, ctx: PipelineContext) -> KnowledgeDebtDetectionResult:
    """Detect knowledge debts and upsert knowledge_debts / assigned_developers."""
    if ctx.session is None:
        raise RuntimeError("knowledge_debt_detection pipeline requires a DB session in the pipeline context")
    session = ctx.session
    now = datetime.now(UTC)
    trace: list[str] = []

    # Reuse the job's shared (read-caching) client when present (agentic backbone), else mint our own.
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=await _mint_installation_token(request.github))
    # per-file signals: {path: {content, age_days, no_review}}
    signals: dict[str, dict] = {}
    commit_sha = ""
    try:
        tree = await client.get_repository_tree(request.owner, request.repo, request.branch)
        source_paths = [t.path for t in tree if t.type == "blob" and _is_source(t.path)][:_MAX_FILES]
        for path in source_paths:
            fc = await client.get_file_content(request.owner, request.repo, path, request.branch)
            commits = await client.list_commits(request.owner, request.repo, path=path, sha=request.branch, per_page=1)
            latest = commits[0] if commits else None
            no_review = True
            if latest is not None:
                pulls = await client.list_commit_pulls(request.owner, request.repo, latest.sha)
                reviewed: set[int] = set()
                for number in pulls:
                    reviews = await client.get_pull_request_reviews(request.owner, request.repo, number)
                    if any(r.state == "APPROVED" for r in reviews):
                        reviewed.add(number)
                no_review = knowledge_analysis.is_no_review(pulls, reviewed)
            signals[path] = {
                "content": fc.content or "",
                "age_days": _age_days(latest.authored_at, now=now) if latest is not None else 0,
                "no_review": no_review,
            }
        head = await client.list_commits(request.owner, request.repo, sha=request.branch, per_page=1)
        commit_sha = head[0].sha if head else ""
    finally:
        if shared_client is None:
            await client.aclose()
    trace.append(f"fetched {len(signals)} source files")

    # AI-generation estimate for the fetched files.
    ai_probs: dict[str, float] = {}
    file_contents = {p: s["content"] for p, s in signals.items() if s["content"]}
    if file_contents:
        try:
            ai_probs = await gemini_stack_service.estimate_ai_generation(file_contents)
        except Exception:
            # 補助的なエンリッチ。Gemini のクォータ超過(429)・一時障害・設定不備などどんな失敗でも、
            # 決定的な理解負債の検知結果を捨てて step 全体を失敗させない（graceful）。
            logger.warning(
                "Gemini AI-generation estimate unavailable; ai_generated reason disabled this run", exc_info=True
            )

    project_id = uuid.UUID(request.project_id)
    job_id = uuid.UUID(request.job_id)
    kc_by_file = await _kc_by_file(session, project_id)
    run = await _get_or_create_run(
        session, job_id=job_id, project_id=project_id, commit_sha=commit_sha, branch=request.branch
    )

    reasons_count: dict[str, int] = {}
    current_keys: set[tuple[str, str]] = set()
    detected = 0
    for path, sig in signals.items():
        ai_prob = ai_probs.get(path, 0.0)
        age_days = sig["age_days"]
        reasons = []
        if knowledge_analysis.is_ai_generated(ai_prob):
            reasons.append(("ai_generated", f"AI 生成痕跡（推定確率 {ai_prob:.2f}）"))
        if knowledge_analysis.is_author_left(age_days):
            reasons.append(("author_left", f"主要 author の最終コミットが {age_days} 日前（離脱/陳腐化の疑い）"))
        if sig["no_review"]:
            reasons.append(("no_review", "レビュー無し / 自動 approve でマージされた痕跡"))
        if not reasons:
            continue

        kc = kc_by_file.get(path, {})
        coverage = kc.get("coverage", 0.0)
        snippet = _snippet(sig["content"])
        for reason, notes in reasons:
            score = knowledge_analysis.reason_score(reason, ai_prob=ai_prob, age_days=age_days)
            debt_id = await _upsert_knowledge_debt(
                session,
                run_id=run.id,
                project_id=project_id,
                repo=request.repo,
                file_path=path,
                reason=reason,
                score=score,
                notes=notes,
                snippet=snippet,
                ai_prob=ai_prob,
                coverage=coverage,
                repay=round(score * 8, 1),
            )
            for handle, dev_kc, certified_via in kc.get("devs", []):
                await _upsert_assigned(
                    session, debt_id=debt_id, handle=handle, coverage=dev_kc, certified_via=certified_via
                )
            current_keys.add((path, reason))
            reasons_count[reason] = reasons_count.get(reason, 0) + 1
            detected += 1

    # Drop this run's knowledge debts no longer produced by the current pass (issue-042).
    stale = delete(KnowledgeDebt).where(col(KnowledgeDebt.run_id) == run.id)
    if current_keys:
        stale = stale.where(tuple_(col(KnowledgeDebt.file_path), col(KnowledgeDebt.reason)).notin_(current_keys))
    await session.execute(stale)

    run.status = JobStatus.COMPLETED
    session.add(run)
    await session.flush()  # run_task owns the terminal commit (atomic with the Job, issue-042)
    trace.append(f"detected {detected} knowledge debts")

    logger.info("knowledge_debt_detection: %s debts for %s/%s@%s", detected, request.owner, request.repo, commit_sha)
    return KnowledgeDebtDetectionResult(
        job_id=request.job_id,
        job_type=JobType.KNOWLEDGE_DEBT_DETECTION,
        status=ResultStatus.COMPLETED,
        project_id=request.project_id,
        run_id=str(run.id),
        commit_sha=commit_sha,
        detected=detected,
        reasons=reasons_count,
        trace=trace,
    )
