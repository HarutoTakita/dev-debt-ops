"""agentic-analysis pipeline (issue 069 → 266) — agent-first repository analysis.

``shared.worker.run_task`` owns the ``Job`` lifecycle (PROCESSING → COMPLETED/FAILED,
idempotency) and writes the returned result into ``Job.result_data``.

Agent-first re-architecture (issue 266): the main repository analysis IS an agent. The pipeline runs
as a sequence of *blocks*:

1. **Base Analysis Agent (block 0)** — the ADK ``run_analysis_agent`` runs FIRST, using the
   exploration MCP toolsets (Serena / GitHub / CodeGraphContext) to produce ONE qualitative
   ``BaseAnalysis`` (features / key concepts / code & knowledge risk narrative), persisted to
   ``base_analysis_snapshots``. This is the "元データ" downstream blocks are meant to consume.
2. **Deterministic backbone** — the existing detection/analysis pipelines (feature clustering →
   code debt → KC → knowledge debt → stack → baseline). Each creates its own ``analysis_run`` keyed
   by ``(job_id, kind)`` and upserts its tables so the Matrix / Galaxy maps populate. All pipelines
   only ``flush``; ``run_task`` commits once.

PR1 (issue 266) is additive: the base agent runs first and its output is persisted, but the
deterministic backbone still fully produces the screen tables (source-of-truth unchanged). Later PRs
make the backbone blocks *consume* ``base_analysis``. A failed/empty base agent never aborts the run
— the deterministic backbone still completes the analysis (graceful degradation).

GitHub token is method B (minted from the Secret Manager-backed App key); Vertex AI uses ADC.
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
from service.agents.runner import run_analysis_agent
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
from service.services.github_git_client import CachingGitHubGitClient, GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.models import BaseAnalysisSnapshot, CodeGraph
from shared.pipelines.context import PipelineContext
from shared.schemas.agentic_analysis import AgenticAnalysisRequest, AgenticAnalysisResult
from shared.schemas.base_analysis import BaseAnalysis
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


async def _persist_base_analysis(session: AsyncSession, project_id: str, base: BaseAnalysis) -> None:
    """Upsert the project's latest Base Analysis Agent output (issue 266). Flush only; run_task commits."""
    now = datetime.now(UTC)
    pid = uuid.UUID(project_id)
    payload = base.model_dump()
    stmt = pg_insert(BaseAnalysisSnapshot).values(id=uuid.uuid4(), project_id=pid, computed_at=now, payload=payload)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_base_analysis_snapshots_project", set_={"computed_at": now, "payload": payload}
    )
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
    """Run the Base Analysis Agent (block 0) then the deterministic backbone (produces map data)."""
    if ctx.session is None:
        raise RuntimeError("agentic_analysis pipeline requires a DB session in the pipeline context")

    steps: list[str] = []
    reporter = ProgressReporter(request.job_id, AGENTIC_STEPS)
    session = ctx.session

    # 1) Base Analysis Agent — the FIRST block (agent-first, issue 266). Shallow-clone so the agent
    # can navigate the repo via Serena (LSP); a failed clone just disables Serena. A failed/empty run
    # never aborts the analysis — the deterministic backbone below still produces the screen tables.
    # NOTE: the progress key stays "twin_agent" in PR1 to avoid frontend churn (renamed in PR5).
    await reporter.start("twin_agent")
    agent_trace: list[str] = []
    base_analysis = BaseAnalysis()
    budget = RunBudget()
    token = await _mint_installation_token(request.github)
    client = GitHubGitClient(access_token=token)
    repo_dir = await repo_checkout.shallow_clone(request.owner, request.repo, request.branch, token)
    # マクロ俯瞰用のコードグラフを事前構築（issue 235）。失敗してもグラフ無しで継続（graceful）。CGC スナップショット
    # ＋ clone からの決定的スナップショット（issue 250）をマージし、CGC が索引失敗/関数 0 件でも理解度マップの
    # L2/L3 が「どんな repo でも」表示される。マージ結果が空＝一時的失敗のときは上書きせず前回を温存。
    cgc_snapshot: dict = {}
    if repo_dir is not None and await code_graph.build_graph(repo_dir):
        cgc_snapshot = await code_graph.extract_snapshot(repo_dir)
    det_snapshot = function_graph.build_snapshot(function_graph.read_repo_sources(repo_dir)) if repo_dir else {}
    snapshot = code_graph.merge_snapshots(cgc_snapshot, det_snapshot)
    if snapshot:
        await _persist_code_graph(session, request.project_id, snapshot)
    try:
        agent_trace, base_analysis = await run_analysis_agent(
            client=client,
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            budget=budget,
            repo_dir=repo_dir,
            github_token=token,
        )
        if not base_analysis.is_empty():
            await _persist_base_analysis(session, request.project_id, base_analysis)
        await reporter.complete("twin_agent")
    except Exception as exc:
        # ベース解析エージェントはベストエフォート。Gemini の一時障害（502/503/500 等）やツール失敗で例外化しても、
        # 決定的バックボーン（機能/コード負債/理解度/学習・クイズ）まで失って解析全体を FAILED＝run_task が全 flush を
        # ロールバック、にしてはならない。ログを残し、元データ無しで決定的バックボーンを実行して COMPLETED に確定する。
        logger.exception("base analysis agent failed; continuing with the deterministic backbone")
        agent_trace = [f"[analysis_agent] failed: {exc}"]
        base_analysis = BaseAnalysis()
        await reporter.fail("twin_agent")
    finally:
        await client.aclose()
        if repo_dir is not None:
            shutil.rmtree(repo_dir, ignore_errors=True)

    # 2) Deterministic backbone — each sub-pipeline runs under THIS job_id, creating its own
    # (job_id, kind) run and upserting its tables on the shared session (flush only). Order:
    # feature clustering first (learning/quiz depend on it), then code debt, KC, knowledge debt.
    # 取得の共通化: バックボーン全体で 1 つの読み取りキャッシュ付き GitHub クライアントを共有し、各ステップが
    # 個別に行っていたリポジトリツリー取得（〜5×）・重複するソースファイル取得を 1 回に集約する。標準呼び出し
    # （各パイプライン単体）では ctx.github_client は None のまま＝各自で取得する従来どおりの動作になる。
    ctx.github_client = CachingGitHubGitClient(access_token=await _mint_installation_token(request.github))
    try:
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
        # agent-first (issue 268): consume the Base Analysis Agent's features when present; else the
        # deterministic clustering runs as fallback (clusters=None). This is the "features" block.
        base_clusters = [f.model_dump() for f in base_analysis.features] or None
        await _run_backbone_step(
            "feature_clustering",
            lambda: feature_clustering.process(fc_req, ctx, clusters=base_clusters),
            steps,
            reporter,
        )
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
        # agent-first (issue 271): enrich deterministic code debts with the agent's rationale (notes
        # only; scores/severity stay deterministic). Empty base → base_findings=None (no change).
        base_code_findings = [f.model_dump() for f in base_analysis.code_findings] or None
        await _run_backbone_step(
            "code_debt_detection",
            lambda: code_debt_detection.process(cd_req, ctx, base_findings=base_code_findings),
            steps,
            reporter,
        )
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
        async def _populate_stack() -> None:
            await stack_analysis.populate_tech_stack(
                ctx.github_client, session, request.owner, request.repo, request.branch
            )

        await _run_backbone_step("stack_analysis", _populate_stack, steps, reporter)

        # 2b) Learning plans + baseline quizzes per feature (server-side, no browser orchestration).
        await reporter.start("baseline")

        async def _on_baseline_progress(done: int, total: int) -> None:
            await reporter.update("baseline", done=done, total=total)

        steps.extend(
            await baseline_generation.generate_learning_and_quizzes(request, ctx, on_progress=_on_baseline_progress)
        )
        await reporter.complete("baseline")
    finally:
        # 共有クライアントを必ず閉じる。
        await ctx.github_client.aclose()
        ctx.github_client = None

    all_trace = agent_trace + steps
    summary = agent_trace[-1] if agent_trace else (steps[-1] if steps else "analysis produced no trace")
    logger.info(
        "agentic_analysis done owner=%s repo=%s agent_trace=%d backbone=%d base(features=%d,code=%d,knowledge=%d)",
        request.owner,
        request.repo,
        len(agent_trace),
        len(steps),
        len(base_analysis.features),
        len(base_analysis.code_findings),
        len(base_analysis.knowledge_findings),
    )
    return AgenticAnalysisResult(
        job_id=request.job_id,
        job_type=JobType.AGENTIC_ANALYSIS,
        status=ResultStatus.COMPLETED,
        owner=request.owner,
        repo=request.repo,
        branch=request.branch,
        summary=summary,
        agent_trace=all_trace,
        recommendations=[],  # 判断レイヤ廃止に向け空（PR5 でフィールド自体を削除）
    )
