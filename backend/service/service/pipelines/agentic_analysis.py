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
from collections.abc import Awaitable, Callable

from service import config
from service.agents.budget import RunBudget
from service.agents.runner import run_twin_agent
from service.pipelines import (
    baseline_generation,
    code_debt_detection,
    feature_clustering,
    kc_analysis,
    knowledge_debt_detection,
)
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
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


async def _run_backbone_step(name: str, run: Callable[[], Awaitable[object]], steps: list[str]) -> None:
    """Run one backbone sub-pipeline; record success/failure (a failure never aborts the run)."""
    try:
        await run()
        steps.append(f"[backbone] {name} done")
    except Exception as exc:
        logger.exception("agentic backbone step failed: %s", name)
        steps.append(f"[backbone] {name} failed: {exc}")


async def process(request: AgenticAnalysisRequest, ctx: PipelineContext) -> AgenticAnalysisResult:
    """Run the deterministic backbone (produces map data) then the Twin Agent judgement layer."""
    if ctx.session is None:
        raise RuntimeError("agentic_analysis pipeline requires a DB session in the pipeline context")

    # 1) Deterministic backbone — each sub-pipeline runs under THIS job_id, creating its own
    # (job_id, kind) run and upserting its tables on the shared session (flush only). Order:
    # feature clustering first (learning/quiz depend on it), then code debt, KC, knowledge debt.
    steps: list[str] = []
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
    await _run_backbone_step("feature_clustering", lambda: feature_clustering.process(fc_req, ctx), steps)
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
    await _run_backbone_step("code_debt_detection", lambda: code_debt_detection.process(cd_req, ctx), steps)
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
    await _run_backbone_step("kc_analysis", lambda: kc_analysis.process(kc_req, ctx), steps)
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
    await _run_backbone_step("knowledge_debt_detection", lambda: knowledge_debt_detection.process(kd_req, ctx), steps)

    # 1b) Learning plans + baseline quizzes per feature (server-side, no browser orchestration).
    steps.extend(await baseline_generation.generate_learning_and_quizzes(request, ctx))

    # 2) Twin Agent judgement layer (autonomous cross-signal risk judgement + remediation).
    budget = RunBudget()
    token = await _mint_installation_token(request.github)
    client = GitHubGitClient(access_token=token)
    try:
        trace, recommendations = await run_twin_agent(
            client=client,
            owner=request.owner,
            repo=request.repo,
            branch=request.branch,
            budget=budget,
        )
    finally:
        await client.aclose()

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
