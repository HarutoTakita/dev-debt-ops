"""agentic-analysis pipeline (issue 069) — the ADK Twin Agent IS the repository analysis.

``shared.worker.run_task`` owns the ``Job`` lifecycle (PROCESSING → COMPLETED/FAILED,
idempotency) and writes the returned result into ``Job.result_data``.

Per issue 069 ("決定的＝ツール / 判断＝エージェント"), this pipeline produces the screen-filling
outputs itself:

1. **Deterministic backbone** — runs the existing detection/analysis pipelines (feature
   clustering → code debt → KC → knowledge debt) on the shared session under THIS job, so each
   creates its own ``analysis_run`` keyed by ``(job_id, kind)`` and upserts its tables
   (``features`` / ``code_debts`` / ``file_kc`` / ``knowledge_debts``). This guarantees the
   Matrix / Galaxy maps populate. All pipelines only ``flush``; ``run_task`` commits once.
2. **Judgement layer** — the ADK Twin Agent (coordinator + knowledge/code specialists +
   remediation strategist, in a LoopAgent) runs on top to produce the cross-signal risk
   judgement and remediation recommendations recorded in ``result_data``.

GitHub token is method B (minted from the Secret Manager-backed App key); Vertex AI uses ADC.
Learning-plan / quiz generation stay as their own fan-out steps (api ``baseline-plans`` /
``baseline-quizzes``), driven by the cockpit after this job produces the feature clustering.
"""

import logging
import shutil
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from service import config
from service.agents.budget import RunBudget
from service.agents.runner import run_twin_agent
from service.pipelines import (
    baseline_generation,
    code_debt_detection,
    feature_clustering,
    kc_analysis,
    knowledge_debt_detection,
    stack_analysis,
)
from service.pipelines.progress import AGENTIC_STEPS, ProgressReporter
from service.services import code_graph, function_graph, repo_checkout
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.models import CodeGraph
from shared.pipelines.context import PipelineContext
from shared.schemas.agentic_analysis import AgenticAnalysisRequest, AgenticAnalysisResult
from shared.schemas.code_debt_detection import CodeDebtDetectionRequest
from shared.schemas.feature_clustering import FeatureClusteringRequest
from shared.schemas.kc_analysis import KcAnalysisRequest
from shared.schemas.knowledge_debt_detection import KnowledgeDebtDetectionRequest
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)


async def _mint_installation_token(github: GitHubRef) -> str:
    """Resolve a GitHub installation token (method B: mint from the Secret Manager key)."""
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


async def _persist_code_graph(session: AsyncSession, project_id: str, graph: dict) -> None:
    """Upsert the project's latest CodeGraphContext snapshot (issue 235). Flush only; run_task commits."""
    now = datetime.now(UTC)
    pid = uuid.UUID(project_id)
    stmt = pg_insert(CodeGraph).values(id=uuid.uuid4(), project_id=pid, computed_at=now, graph=graph)
    stmt = stmt.on_conflict_do_update(constraint="uq_code_graphs_project", set_={"computed_at": now, "graph": graph})
    await session.execute(stmt)
    await session.flush()


async def _run_backbone_step(
    name: str,
    run: Callable[[], Awaitable[object]],
    steps: list[str],
    reporter: ProgressReporter | None = None,
) -> None:
    """Run one backbone sub-pipeline; record success/failure (a failure never aborts the run).

    ``name`` doubles as the progress step key (matches ``AGENTIC_STEPS``), so the reporter reflects
    each step's running → completed/failed transition for the live cockpit.
    """
    if reporter is not None:
        await reporter.start(name)
    try:
        await run()
        steps.append(f"[backbone] {name} done")
        if reporter is not None:
            await reporter.complete(name)
    except Exception as exc:
        logger.exception("agentic backbone step failed: %s", name)
        steps.append(f"[backbone] {name} failed: {exc}")
        if reporter is not None:
            await reporter.fail(name)


async def process(request: AgenticAnalysisRequest, ctx: PipelineContext) -> AgenticAnalysisResult:
    """Run the deterministic backbone (produces map data) then the Twin Agent judgement layer."""
    if ctx.session is None:
        raise RuntimeError("agentic_analysis pipeline requires a DB session in the pipeline context")

    # 1) Deterministic backbone — each sub-pipeline runs under THIS job_id, creating its own
    # (job_id, kind) run and upserting its tables on the shared session (flush only). Order:
    # feature clustering first (learning/quiz depend on it), then code debt, KC, knowledge debt.
    steps: list[str] = []
    reporter = ProgressReporter(request.job_id, AGENTIC_STEPS)
    fc_req = FeatureClusteringRequest(
        job_id=request.job_id,
        job_type=JobType.FEATURE_CLUSTERING,
        owner=request.owner,
        repo=request.repo,
        branch=request.branch,
        github=request.github,
        requested_by=request.requested_by,
        project_id=request.project_id,
    )
    await _run_backbone_step("feature_clustering", lambda: feature_clustering.process(fc_req, ctx), steps, reporter)
    cd_req = CodeDebtDetectionRequest(
        job_id=request.job_id,
        job_type=JobType.CODE_DEBT_DETECTION,
        owner=request.owner,
        repo=request.repo,
        branch=request.branch,
        github=request.github,
        requested_by=request.requested_by,
        project_id=request.project_id,
    )
    await _run_backbone_step("code_debt_detection", lambda: code_debt_detection.process(cd_req, ctx), steps, reporter)
    kc_req = KcAnalysisRequest(
        job_id=request.job_id,
        job_type=JobType.KC_ANALYSIS,
        owner=request.owner,
        repo=request.repo,
        branch=request.branch,
        github=request.github,
        requested_by=request.requested_by,
        project_id=request.project_id,
    )
    await _run_backbone_step("kc_analysis", lambda: kc_analysis.process(kc_req, ctx), steps, reporter)
    kd_req = KnowledgeDebtDetectionRequest(
        job_id=request.job_id,
        job_type=JobType.KNOWLEDGE_DEBT_DETECTION,
        owner=request.owner,
        repo=request.repo,
        branch=request.branch,
        github=request.github,
        requested_by=request.requested_by,
        project_id=request.project_id,
    )
    await _run_backbone_step(
        "knowledge_debt_detection", lambda: knowledge_debt_detection.process(kd_req, ctx), steps, reporter
    )
    # Tech-stack detection (issue 068): populates ``tech_stacks`` (owner/repo keyed) so the learning
    # plan's "技術スタックを学ぶ" section has source terms. Must run before baseline generation below.
    # Use the *deterministic* populate (not the ADK stack agent, which sometimes skips save_stack).
    session = ctx.session

    async def _populate_stack() -> None:
        token = await _mint_installation_token(request.github)
        client = GitHubGitClient(access_token=token)
        try:
            await stack_analysis.populate_tech_stack(client, session, request.owner, request.repo, request.branch)
        finally:
            await client.aclose()

    await _run_backbone_step("stack_analysis", _populate_stack, steps, reporter)

    # 1b) Learning plans + baseline quizzes per feature (server-side, no browser orchestration).
    await reporter.start("baseline")

    async def _on_baseline_progress(done: int, total: int) -> None:
        await reporter.update("baseline", done=done, total=total)

    steps.extend(
        await baseline_generation.generate_learning_and_quizzes(request, ctx, on_progress=_on_baseline_progress)
    )
    await reporter.complete("baseline")

    # 2) Twin Agent judgement layer (autonomous cross-signal risk judgement + remediation).
    # Shallow-clone the repo so the agent can navigate it semantically via Serena (LSP); a failed
    # clone just disables Serena (the agent falls back to the REST repo tools).
    await reporter.start("twin_agent")
    budget = RunBudget()
    token = await _mint_installation_token(request.github)
    client = GitHubGitClient(access_token=token)
    repo_dir = await repo_checkout.shallow_clone(request.owner, request.repo, request.branch, token)
    # マクロ俯瞰用のコードグラフを事前構築（issue 235）。失敗してもエージェントはグラフ無しで継続（graceful）。
    # 構築できたら CGC スナップショットを抽出し、加えて clone から決定的スナップショット（issue 250）を作って
    # マージする。これで CGC が索引失敗/関数 0 件でも、理解度マップの L2/L3 が「どんな repo でも」表示される
    # （CGC 優先・決定的が埋める）。マージ結果が空＝一時的失敗のときは上書きせず前回のスナップショットを温存。
    cgc_snapshot: dict = {}
    if repo_dir is not None and await code_graph.build_graph(repo_dir):
        cgc_snapshot = await code_graph.extract_snapshot(repo_dir)
    det_snapshot = function_graph.build_snapshot(function_graph.read_repo_sources(repo_dir)) if repo_dir else {}
    snapshot = code_graph.merge_snapshots(cgc_snapshot, det_snapshot)
    if snapshot:
        await _persist_code_graph(session, request.project_id, snapshot)
    try:
        trace, recommendations = await run_twin_agent(
            client=client,
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            budget=budget,
            repo_dir=repo_dir,
            github_token=token,
        )
        await reporter.complete("twin_agent")
    except Exception as exc:
        # Twin Agent は判断レイヤ（ベストエフォート）。Gemini の一時障害（502/503/500 等）やツール失敗で例外化
        # しても、決定的バックボーン（コード負債/理解度/機能/学習・クイズ）の成果まで失って解析全体を
        # FAILED＝run_task が全 flush をロールバック、にしてはならない。ログを残し、推奨なしで解析は COMPLETED
        # として確定する（graceful degradation）。これにより一時的な 502 で解析全体が飛ぶ／終了状態に到達せず
        # コックピットが「処理中」のまま固まる、という問題を防ぐ。
        logger.exception("twin agent failed; completing analysis without agent recommendations")
        trace, recommendations = [f"[twin_agent] failed: {exc}"], []
        await reporter.fail("twin_agent")
    finally:
        await client.aclose()
        if repo_dir is not None:
            shutil.rmtree(repo_dir, ignore_errors=True)

    agent_trace = steps + trace
    summary = trace[-1] if trace else (steps[-1] if steps else "Twin Agent run produced no trace")
    logger.info(
        "agentic_analysis done owner=%s repo=%s backbone=%d trace=%d recommendations=%d",
        request.owner,
        request.repo,
        len(steps),
        len(trace),
        len(recommendations),
    )
    return AgenticAnalysisResult(
        job_id=request.job_id,
        job_type=JobType.AGENTIC_ANALYSIS,
        status=ResultStatus.COMPLETED,
        owner=request.owner,
        repo=request.repo,
        branch=request.branch,
        summary=summary,
        agent_trace=agent_trace,
        recommendations=recommendations,
    )
