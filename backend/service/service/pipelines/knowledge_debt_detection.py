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
from service.pipelines.run_cleanup import prune_superseded_runs
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
    except (ValueError, TypeError):
        return 0
    # TZ 無し（date-only や offset 欠落）の場合、aware な now との減算が TypeError になるため UTC を補完する。
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
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
                AnalysisRun.status == JobStatus.COMPLETED.value,  # ty: ignore[invalid-argument-type]
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
    # 実装が始まる行から抜粋する（先頭の docstring / import だけを切り出して自然言語プロースになるのを防ぐ）。
    return "\n".join(code_analysis.implementation_excerpt(content).splitlines()[:_MAX_SNIPPET_LINES])


def _agent_notes_by_file(base_findings: list[dict] | None) -> dict[str, str]:
    """Collapse the Base Analysis Agent's knowledge findings into one rationale string per file.

    Used to *enrich* deterministic ``detection_notes`` — KC / coverage / scores stay deterministic
    (issue 273, locked decision #3).
    """
    notes: dict[str, list[str]] = {}
    for raw in base_findings or []:
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("file_path") or "").strip()
        rationale = str(raw.get("rationale") or "").strip()
        if path and rationale:
            notes.setdefault(path, []).append(rationale)
    return {path: " / ".join(dict.fromkeys(rs)) for path, rs in notes.items()}


async def _prior_completed_kd_run(session: AsyncSession, project_id: uuid.UUID) -> AnalysisRun | None:
    """The project's latest COMPLETED knowledge_debt run (the carry-forward source)."""
    return (
        (
            await session.execute(
                select(AnalysisRun)
                .where(
                    col(AnalysisRun.project_id) == project_id,
                    col(AnalysisRun.kind) == JobType.KNOWLEDGE_DEBT_DETECTION.value,
                    col(AnalysisRun.status) == JobStatus.COMPLETED,
                )
                .order_by(col(AnalysisRun.created_at).desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def _carry_forward_knowledge_debts(
    session: AsyncSession,
    *,
    prior_run_id: uuid.UUID,
    new_run_id: uuid.UUID,
    keep_files: set[str],
    kc_by_file: dict[str, dict],
) -> set[tuple[str, str]]:
    """Copy the prior run's KnowledgeDebt rows for unchanged files into the new run.

    Re-derives assigned developers from the current KC. Returns the carried ``(file_path, reason)`` keys
    so the stale-delete keeps them. Knowledge findings are per-file (no cross-file coupling) — exact.
    """
    rows = (
        (await session.execute(select(KnowledgeDebt).where(col(KnowledgeDebt.run_id) == prior_run_id))).scalars().all()
    )
    carried: set[tuple[str, str]] = set()
    for r in rows:
        if r.file_path not in keep_files:
            continue
        new = KnowledgeDebt(
            id=uuid.uuid4(),
            project_id=r.project_id,
            run_id=new_run_id,
            file_path=r.file_path,
            repo=r.repo,
            reason=r.reason,
            severity=r.severity,
            status=r.status,
            related_adr=r.related_adr,
            code_snippet=r.code_snippet,
            code_debt_score=r.code_debt_score,
            knowledge_coverage=r.knowledge_coverage,
            ai_generation_prob=r.ai_generation_prob,
            estimated_repay_hours=r.estimated_repay_hours,
            detection_notes=r.detection_notes,
            metrics=r.metrics,
            detected_at=r.detected_at,
            created_at=r.created_at,
        )
        session.add(new)
        await session.flush()
        for handle, dev_kc, certified_via in kc_by_file.get(r.file_path, {}).get("devs", []):
            await _upsert_assigned(session, debt_id=new.id, handle=handle, coverage=dev_kc, certified_via=certified_via)
        carried.add((r.file_path, r.reason))
    return carried


async def process(
    request: KnowledgeDebtDetectionRequest,
    ctx: PipelineContext,
    *,
    base_findings: list[dict] | None = None,
    changed_paths: set[str] | None = None,
    head_sha: str | None = None,
) -> KnowledgeDebtDetectionResult:
    """Detect knowledge debts and upsert knowledge_debts / assigned_developers.

    ``base_findings`` (issue 273, agent-first): when provided — the Base Analysis Agent's
    ``BaseAnalysis.knowledge_findings`` — the agent's rationale for a file is appended to that file's
    ``detection_notes``. KC / coverage / scores stay deterministic. ``None`` → behaviour unchanged.

    ``changed_paths`` (Phase 2b incremental): when a prior run exists and ``changed_paths`` is not None,
    only changed files run the (expensive per-file) signal probe + AI estimate; unchanged files' debts
    are carried forward from the prior run. Findings are per-file, so this is exact (no neighbor
    expansion needed). ``None`` → full recompute.
    """
    if ctx.session is None:
        raise RuntimeError("knowledge_debt_detection pipeline requires a DB session in the pipeline context")
    session = ctx.session
    now = datetime.now(UTC)
    trace: list[str] = []
    project_id = uuid.UUID(request.project_id)
    prior_run = await _prior_completed_kd_run(session, project_id)
    do_incremental = prior_run is not None and changed_paths is not None

    # Reuse the job's shared (read-caching) client when present (agentic backbone), else mint our own.
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=await _mint_installation_token(request.github))
    # per-file signals: {path: {content, age_days, no_review}}
    signals: dict[str, dict] = {}
    commit_sha = ""
    source_paths: list[str] = []
    try:
        tree = await client.get_repository_tree(request.owner, request.repo, request.branch)
        source_paths = [t.path for t in tree if t.type == "blob" and _is_source(t.path)][:_MAX_FILES]
        # 差分再解析（Phase 2b）: 変更ファイルだけ高価な signal 収集（PR レビュー API + AI）を回す。未変更は
        # 前 run から持ち越す。findings は per-file 完結なので近傍拡張は不要。
        to_process = [p for p in source_paths if p in changed_paths] if do_incremental else source_paths
        for path in to_process:
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
        if head_sha:
            commit_sha = head_sha
        else:
            head = await client.list_commits(request.owner, request.repo, sha=request.branch, per_page=1)
            commit_sha = head[0].sha if head else ""
    finally:
        if shared_client is None:
            await client.aclose()
    trace.append(f"probed {len(signals)} files (incremental={do_incremental})")

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

    job_id = uuid.UUID(request.job_id)
    agent_notes = _agent_notes_by_file(base_findings)  # agent-first (issue 273): notes enrichment
    kc_by_file = await _kc_by_file(session, project_id)
    run = await _get_or_create_run(
        session, job_id=job_id, project_id=project_id, commit_sha=commit_sha, branch=request.branch
    )

    # 差分再解析: 未変更ファイルの前 run debt を新 run へ持ち越す（assigned は現在 KC から再導出）。carried
    # キーは stale-delete から守るため current_keys に seed する。
    reasons_count: dict[str, int] = {}
    current_keys: set[tuple[str, str]] = set()
    if do_incremental and prior_run is not None:
        current_keys = await _carry_forward_knowledge_debts(
            session,
            prior_run_id=prior_run.id,
            new_run_id=run.id,
            keep_files=set(source_paths) - {p for p in signals},
            kc_by_file=kc_by_file,
        )
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
        agent_note = agent_notes.get(path)
        for reason, notes in reasons:
            if agent_note:
                notes = f"{notes}\n\n【エージェント所見】{agent_note}"
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
    # 再解析で古い run の knowledge_debts が溜まるのを防ぐ（最新 run のみ残す）。
    await prune_superseded_runs(
        session, project_id=run.project_id, kind=JobType.KNOWLEDGE_DEBT_DETECTION.value, keep_run_id=run.id
    )
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
