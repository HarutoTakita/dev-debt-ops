"""agentic-analysis pipeline (issue 069) — runs the ADK Twin Agent over a repository.

``shared.worker.run_task`` owns the ``Job`` lifecycle (PROCESSING → COMPLETED/FAILED,
idempotency) and writes the returned result into ``Job.result_data``. This pipeline is additive:
it orchestrates the same deterministic analysis as tools (issue 069 keeps the existing pipelines
as the tool implementations), with the Twin Agent making the judgement calls. GitHub token is
method B (minted from the Secret Manager-backed App key); Vertex AI uses ADC (no API key).
"""

import logging

from service import config
from service.agents.budget import RunBudget
from service.agents.runner import run_twin_agent
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.pipelines.context import PipelineContext
from shared.schemas.agentic_analysis import AgenticAnalysisRequest, AgenticAnalysisResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)


async def _mint_installation_token(github: GitHubRef) -> str:
    """Resolve a GitHub installation token (method B: mint from the Secret Manager key)."""
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


async def process(request: AgenticAnalysisRequest, ctx: PipelineContext) -> AgenticAnalysisResult:
    """Run the Twin Agent for the repository and return its trace + summary."""
    if ctx.session is None:
        raise RuntimeError("agentic_analysis pipeline requires a DB session in the pipeline context")

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

    summary = trace[-1] if trace else "Twin Agent run produced no trace"
    logger.info(
        "agentic_analysis done owner=%s repo=%s trace_lines=%d recommendations=%d",
        request.owner,
        request.repo,
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
        agent_trace=trace,
        recommendations=recommendations,
    )
