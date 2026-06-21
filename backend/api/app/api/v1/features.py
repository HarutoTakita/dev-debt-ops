"""Feature-clustering API (issue 052) — enqueue + 202 (delivery is issue 055).

``POST .../cluster-features`` enqueues the ``feature_clustering`` pipeline (Gemini groups the
repo's files into product features). It is enqueue-only (method B); the frontend polls
``GET /jobs/{id}``. Serving feature data (feature list / per-feature files + rolled-up KC/debts)
is issue 055.
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

router = APIRouter(tags=["features"])


@router.post(
    "/orgs/{slug}/projects/{project_slug}/cluster-features",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="機能クラスタリング（feature_clustering）を非同期ジョブとして enqueue する",
)
async def cluster_features(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> JobEnqueuedOut:
    """Enqueue Gemini feature clustering for the project's repo (method B) and return ``202``."""
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
        job_type=JobType.FEATURE_CLUSTERING,
        payload=payload,
        created_by=current_user.id,
        project_id=project.id,
    )
    return JobEnqueuedOut(job_id=job.id, status=job.status)
