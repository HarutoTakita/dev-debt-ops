"""Agentic-analysis trigger (issue 069).

``POST .../agentic-analysis`` enqueues an ``agentic_analysis`` Job (ADK Twin Agent) for the
project's repository and returns ``202`` immediately — the Twin Agent (knowledge/code
specialists + remediation strategist, wrapped in a LoopAgent) runs in the ``service`` container
off the request path. The frontend polls ``GET /jobs/{job_id}`` for the trace + recommendations.
Same issue-018 enqueue pattern as ``detect-debts``; method B keeps the GitHub secret off the queue.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.api.deps import CurrentUser, OrgScope, SessionDep
from app.api.v1.github import InstallationIdDep
from app.schemas.job import JobEnqueuedOut
from app.services.dependencies import get_blob_client, get_task_dispatcher
from app.services.job_orchestrator import enqueue_job
from app.services.project import ProjectServiceDep
from shared.enums import JobType
from shared.queue import BlobClient, TaskDispatcher

router = APIRouter(tags=["agentic"])


@router.post(
    "/orgs/{slug}/projects/{project_slug}/agentic-analysis",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="ADK Twin Agent による agentic 解析を非同期ジョブとして enqueue する",
)
async def trigger_agentic_analysis(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> JobEnqueuedOut:
    """Enqueue an ``agentic_analysis`` job for the project's repository and return ``202``."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    payload = {
        "owner": project.repo_owner,
        "repo": project.repo_name,
        "branch": project.default_branch or "main",
        "requested_by": str(current_user.id),  # audit only
        "project_id": str(project.id),
        "github": {"installation_id": installation_id},
    }
    job = await enqueue_job(
        session=session,
        dispatcher=dispatcher,
        blob_client=blob,
        job_type=JobType.AGENTIC_ANALYSIS,
        payload=payload,
        created_by=current_user.id,
        project_id=project.id,
    )
    return JobEnqueuedOut(job_id=job.id, status=job.status)
