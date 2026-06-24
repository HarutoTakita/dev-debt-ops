"""code-walkthrough-generation pipeline (on-demand fallback).

Generates an ordered, line-anchored walkthrough (line ranges + Japanese explanations) for one
"understand this code" learning resource. Walkthroughs are normally pre-generated during learning-plan
generation; this pipeline is the on-demand fallback for files that were not pre-generated (e.g. plans
created before pre-generation, or files that failed). The result is persisted on
``learning_resources.walkthrough`` and the build is idempotent (skip if already generated).
``shared.worker.run_task`` owns the terminal commit (issue 042).
"""

import logging
import uuid

from sqlalchemy import select
from sqlmodel import col

from service import config
from service.services.code_walkthrough import build_walkthrough
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.models import LearningResource
from shared.pipelines.context import PipelineContext
from shared.schemas.learning_plan import CodeWalkthroughGenerationRequest, CodeWalkthroughGenerationResult
from shared.schemas.stack_analysis import GitHubRef

logger = logging.getLogger(__name__)


async def _mint_installation_token(github: GitHubRef) -> str:
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


def _result(request: CodeWalkthroughGenerationRequest, *, step_count: int) -> CodeWalkthroughGenerationResult:
    return CodeWalkthroughGenerationResult(
        job_id=request.job_id,
        job_type=JobType.CODE_WALKTHROUGH_GENERATION,
        status=ResultStatus.COMPLETED,
        resource_id=request.resource_id,
        step_count=step_count,
    )


async def process(request: CodeWalkthroughGenerationRequest, ctx: PipelineContext) -> CodeWalkthroughGenerationResult:
    """Fetch the resource's file, generate a line-anchored walkthrough, and persist it (idempotent)."""
    if ctx.session is None:
        raise RuntimeError("code_walkthrough_generation pipeline requires a DB session in the pipeline context")
    session = ctx.session

    resource = (
        await session.execute(
            select(LearningResource).where(col(LearningResource.id) == uuid.UUID(request.resource_id))
        )
    ).scalar_one_or_none()
    if resource is None:
        return _result(request, step_count=0)
    if resource.walkthrough:  # idempotent: already generated
        return _result(request, step_count=len(resource.walkthrough))

    owner, _, repo = request.repo_full_name.partition("/")
    if not owner or not repo or not resource.source_ref:
        return _result(request, step_count=0)

    token = await _mint_installation_token(request.github)
    client = GitHubGitClient(access_token=token)
    try:
        steps = await build_walkthrough(client, owner, repo, resource.source_ref, request.ref)
    finally:
        await client.aclose()

    resource.walkthrough = steps
    session.add(resource)
    await session.flush()  # run_task owns the terminal commit (issue 042)

    logger.info("code_walkthrough_generation: %s steps for resource %s", len(steps), request.resource_id)
    return _result(request, step_count=len(steps))
