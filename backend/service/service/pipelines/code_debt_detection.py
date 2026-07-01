"""code-debt-detection pipeline (issue 028).

Fetches a repository snapshot via ``GitHubGitClient`` (method B token), runs the MVP static
analysis (complexity / duplication / dead code) plus a Gemini AI-generation estimate, and
upserts the findings into ``code_debts`` under an ``analysis_run``. ``shared.worker.run_task``
owns the ``Job`` lifecycle and writes the returned summary into ``Job.result_data``.

Idempotent across Cloud Tasks at-least-once redelivery: the ``analysis_run`` is keyed by
``job_id`` (reused on retry) and ``code_debts`` upsert on ``(run_id, file_path, type)``.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from service import config
from service.services import code_analysis, gemini_stack_service, semgrep_scan
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobStatus, JobType, ResultStatus
from shared.models import AnalysisRun, CodeDebt
from shared.pipelines.context import PipelineContext
from shared.schemas.code_debt_detection import CodeDebtDetectionRequest, CodeDebtDetectionResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)

_MAX_FILES = 100  # cap files fetched/analysed per run (REST budget; MVP)
_MAX_SNIPPET_LINES = 20
_DEAD_SCORE = 0.5  # dead code is a fixed medium-severity finding


@dataclass
class Finding:
    """One detected code-debt finding before persistence (typed for ty-clean float maths)."""

    file_path: str
    type: str
    score: float
    archaeology_notes: str
    code_snippet: str
    estimated_repay_hours: float
    metrics: dict = field(default_factory=dict)
    ai_generation_prob: float = 0.0


async def _mint_installation_token(github: GitHubRef) -> str:
    """Method B: use an explicit access_token if present, else mint from the Secret Manager key."""
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


def _snippet(content: str) -> str:
    return "\n".join(content.splitlines()[:_MAX_SNIPPET_LINES])


# 「なぜ品質が低いか」の説明文（解析時に生成）。指標値だけでなく、理由・影響・改善の方向まで
# 1 つの文章で示し、コード改善ビューでそのまま読めるようにする（issue 210）。
def _complexity_notes(cc: int) -> str:
    return (
        f"循環的複雑度が {cc} と高く、条件分岐やネストが深いため処理の流れを追いにくくなっています。"
        "変更時に想定外の経路を見落としてバグを埋め込みやすい状態です。"
        "責務ごとに関数を分割したりガード節を導入したりすることで複雑度を下げられます。"
    )


def _duplicate_notes(ratio: float) -> str:
    pct = round(ratio * 100)
    return (
        f"ほぼ同じコードブロックがこのファイルの約 {pct}% を占めています。"
        "重複は修正漏れの温床になり、1 箇所の変更を複数箇所へ反映する保守コストを生みます。"
        "共通処理を関数やモジュールへ抽出して一本化することを推奨します。"
    )


def _dead_notes(loc: int) -> str:
    return (
        f"このファイル（約 {loc} 行）はどのモジュールからも import されておらず、"
        "到達不能な未使用コードの可能性が高いです。残置すると読み手の認知負荷や誤った改修のリスクになるため、"
        "参照の有無を確認のうえ削除を検討してください。"
    )


def detect(files: dict[str, str]) -> list[Finding]:
    """Run all static detectors over ``files`` and return findings (no AI, no DB).

    Pure and deterministic so it is unit-testable without GitHub / Gemini / DB.
    """
    findings: list[Finding] = []

    # Complexity — one finding per file whose cyclomatic complexity is high enough.
    for path, content in files.items():
        if not code_analysis.is_source_file(path):
            continue
        language = "python" if path.lower().endswith(".py") else "ts_js"
        cc = code_analysis.cyclomatic_complexity(content, language)
        if code_analysis.complexity_is_debt(cc):
            findings.append(
                Finding(
                    file_path=path,
                    type="complexity",
                    score=code_analysis.complexity_score(cc),
                    archaeology_notes=_complexity_notes(cc),
                    code_snippet=_snippet(content),
                    metrics={"cyclomatic_complexity": cc},
                    estimated_repay_hours=round(cc / 4, 1),
                )
            )

    # Duplication — normalized-block ratio across the whole file set.
    for path, ratio in code_analysis.find_duplicate_ratios(files).items():
        if code_analysis.duplication_is_debt(ratio):
            score = code_analysis.duplication_score(ratio)
            findings.append(
                Finding(
                    file_path=path,
                    type="duplicate",
                    score=score,
                    archaeology_notes=_duplicate_notes(ratio),
                    code_snippet=_snippet(files[path]),
                    metrics={"duplicate_ratio": round(ratio, 3)},
                    estimated_repay_hours=round(score * 6, 1),
                )
            )

    # Dead code — source files nothing imports (heuristic).
    for path in code_analysis.find_dead_files(files):
        loc = len(files[path].splitlines())
        findings.append(
            Finding(
                file_path=path,
                type="dead",
                score=_DEAD_SCORE,
                archaeology_notes=_dead_notes(loc),
                code_snippet=_snippet(files[path]),
                metrics={"inbound_imports": 0, "loc": loc},
                estimated_repay_hours=round(loc / 100, 1),
            )
        )

    return findings


def _semgrep_to_findings(aggregates: list[semgrep_scan.SemgrepAggregate], files: dict[str, str]) -> list[Finding]:
    """Convert Semgrep per-(file, type) aggregates into code-debt ``Finding`` rows (issue 069).

    Reuses ``_snippet`` for the code preview; ``estimated_repay_hours`` scales with finding count.
    """
    out: list[Finding] = []
    for agg in aggregates:
        count = agg.metrics.get("semgrep_count", 1)
        out.append(
            Finding(
                file_path=agg.file_path,
                type=agg.debt_type,
                score=agg.score,
                archaeology_notes=agg.notes,
                code_snippet=_snippet(files.get(agg.file_path, "")),
                metrics=agg.metrics,
                estimated_repay_hours=round(min(count * 0.5, 8.0), 1),
            )
        )
    return out


async def _get_or_create_run(
    session: AsyncSession, *, job_id: uuid.UUID, project_id: uuid.UUID, commit_sha: str, branch: str
) -> AnalysisRun:
    """Reuse the run for this job (idempotent retry) or create a new PROCESSING run."""
    existing = (
        await session.execute(
            select(AnalysisRun).where(
                col(AnalysisRun.job_id) == job_id,
                col(AnalysisRun.kind) == JobType.CODE_DEBT_DETECTION.value,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    run = AnalysisRun(
        project_id=project_id,
        commit_sha=commit_sha,
        branch=branch,
        kind=JobType.CODE_DEBT_DETECTION.value,
        job_id=job_id,
        status=JobStatus.PROCESSING,
    )
    session.add(run)
    await session.flush()
    return run


async def _upsert_debt(session: AsyncSession, *, run_id: uuid.UUID, project_id: uuid.UUID, finding: Finding) -> None:
    now = datetime.now(UTC)
    severity = code_analysis.quantize_severity(finding.score)
    values = {
        "id": uuid.uuid4(),
        "project_id": project_id,
        "run_id": run_id,
        "file_path": finding.file_path,
        "type": finding.type,
        "severity": severity,
        "status": "open",
        "detected_at": now,
        "archaeology_notes": finding.archaeology_notes,
        "code_snippet": finding.code_snippet,
        "code_debt_score": finding.score,
        "knowledge_coverage": 0.0,  # provisional until 029 (KC) overwrites via join
        "ai_generation_prob": finding.ai_generation_prob,
        "estimated_repay_hours": finding.estimated_repay_hours,
        "metrics": finding.metrics,
    }
    stmt = pg_insert(CodeDebt).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_code_debts_run_file_type",
        set_={
            "severity": severity,
            "status": "open",
            "detected_at": now,
            "archaeology_notes": values["archaeology_notes"],
            "code_snippet": values["code_snippet"],
            "code_debt_score": values["code_debt_score"],
            "ai_generation_prob": values["ai_generation_prob"],
            "estimated_repay_hours": values["estimated_repay_hours"],
            "metrics": values["metrics"],
        },
    )
    await session.execute(stmt)


async def _delete_stale_debts(session: AsyncSession, *, run_id: uuid.UUID, current_keys: set[tuple[str, str]]) -> None:
    """Delete this run's debts no longer produced by the current detection (issue-042).

    Re-running a run (or an at-least-once redelivery) must not leave behind findings that have
    since disappeared (e.g. a file dropped below threshold). Upsert keeps surviving rows' ids
    stable; this removes only the rows whose ``(file_path, type)`` is absent from this pass.
    """
    stmt = delete(CodeDebt).where(col(CodeDebt.run_id) == run_id)
    if current_keys:
        stmt = stmt.where(tuple_(col(CodeDebt.file_path), col(CodeDebt.type)).notin_(current_keys))
    await session.execute(stmt)


async def process(request: CodeDebtDetectionRequest, ctx: PipelineContext) -> CodeDebtDetectionResult:
    """Detect code debts for the repository and upsert them under an analysis run."""
    if ctx.session is None:
        raise RuntimeError("code_debt_detection pipeline requires a DB session in the pipeline context")
    session = ctx.session

    # Reuse the job's shared (read-caching) client when present (agentic backbone), else mint our own
    # for standalone invocation. Only close a client we created — the shared one is owned by the caller.
    shared_client = ctx.github_client
    client = shared_client or GitHubGitClient(access_token=await _mint_installation_token(request.github))
    try:
        tree = await client.get_repository_tree(request.owner, request.repo, request.branch)
        source_paths = [t.path for t in tree if t.type == "blob" and code_analysis.is_source_file(t.path)][:_MAX_FILES]
        files: dict[str, str] = {}
        for path in source_paths:
            fc = await client.get_file_content(request.owner, request.repo, path, request.branch)
            if fc.content is not None:
                files[path] = fc.content
        commits = await client.list_commits(request.owner, request.repo, sha=request.branch, per_page=1)
        commit_sha = commits[0].sha if commits else ""
    finally:
        if shared_client is None:
            await client.aclose()

    findings = detect(files)

    # Real static analysis via Semgrep (security / smell), merged with the heuristic findings.
    # Graceful: scan_files returns [] on any failure, so detection still works without Semgrep.
    findings.extend(_semgrep_to_findings(await semgrep_scan.scan_files(files), files))

    # AI-generation estimate only for files that already have a finding (bounds the Gemini call).
    flagged_paths = {f.file_path for f in findings}
    ai_probs: dict[str, float] = {}
    if flagged_paths:
        try:
            ai_probs = await gemini_stack_service.estimate_ai_generation({p: files[p] for p in flagged_paths})
        except Exception:
            # AI 生成確率は補助的なエンリッチ。Gemini のクォータ超過(429)・一時障害(5xx)・認証/設定不備など
            # どんな失敗でも、決定的な静的解析（Semgrep/ヒューリスティック）の検知結果を捨てて step 全体を
            # 失敗させてはならない。0.0 を既定にして検知は継続する（semgrep_scan と同じく graceful）。
            logger.warning(
                "Gemini AI-generation estimate unavailable; defaulting ai_generation_prob to 0.0", exc_info=True
            )
    for f in findings:
        f.ai_generation_prob = ai_probs.get(f.file_path, 0.0)

    project_id = uuid.UUID(request.project_id)
    job_id = uuid.UUID(request.job_id)
    run = await _get_or_create_run(
        session, job_id=job_id, project_id=project_id, commit_sha=commit_sha, branch=request.branch
    )

    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for finding in findings:
        await _upsert_debt(session, run_id=run.id, project_id=project_id, finding=finding)
        by_type[finding.type] = by_type.get(finding.type, 0) + 1
        sev = code_analysis.quantize_severity(finding.score)
        by_severity[sev] = by_severity.get(sev, 0) + 1

    await _delete_stale_debts(session, run_id=run.id, current_keys={(f.file_path, f.type) for f in findings})

    run.status = JobStatus.COMPLETED
    session.add(run)
    await session.flush()  # run_task owns the terminal commit (atomic with the Job, issue-042)

    logger.info("code_debt_detection: %s findings for %s/%s@%s", len(findings), request.owner, request.repo, commit_sha)
    return CodeDebtDetectionResult(
        job_id=request.job_id,
        job_type=JobType.CODE_DEBT_DETECTION,
        status=ResultStatus.COMPLETED,
        project_id=request.project_id,
        run_id=str(run.id),
        commit_sha=commit_sha,
        detected=len(findings),
        by_type=by_type,
        by_severity=by_severity,
    )
