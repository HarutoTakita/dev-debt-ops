"""Galaxy personal-KC API (issue 032).

``GET .../galaxy`` projects issue 029's latest ``kc_analysis`` run into ``personalGalaxySchema``
(read-only; ``observed=false`` when nothing analysed). ``POST .../analyze-galaxy`` enqueues the
same ``kc_analysis`` pipeline (029) and returns ``202`` — no new pipeline/JobType here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.api.deps import CurrentUser, OrgScope, SASessionDep, SessionDep
from app.api.v1.github import InstallationIdDep
from app.schemas.galaxy import PersonalGalaxyOut
from app.schemas.job import JobEnqueuedOut
from app.services.dependencies import get_blob_client, get_task_dispatcher
from app.services.galaxy_query import build_galaxy
from app.services.job_orchestrator import enqueue_job
from app.services.project import ProjectServiceDep
from shared.enums import JobType
from shared.queue import BlobClient, TaskDispatcher

router = APIRouter(tags=["galaxy"])


@router.get(
    "/orgs/{slug}/projects/{project_slug}/galaxy",
    response_model=PersonalGalaxyOut,
    summary="Knowledge Galaxy 個人 KC マップを返す",
)
async def get_galaxy(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SASessionDep,
) -> PersonalGalaxyOut:
    """Return the developer's personal galaxy. 200 with ``observed=false`` when not yet analysed."""
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    return await build_galaxy(session, project, current_user)


@router.post(
    "/orgs/{slug}/projects/{project_slug}/analyze-galaxy",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="KC 算出（kc_analysis）を非同期ジョブとして enqueue する",
)
async def analyze_galaxy(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> JobEnqueuedOut:
    """Enqueue issue 029's ``kc_analysis`` for the project's repo (method B) and return ``202``."""
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
        job_type=JobType.KC_ANALYSIS,
        payload=payload,
        created_by=current_user.id,
        project_id=project.id,
    )
    return JobEnqueuedOut(job_id=job.id, status=job.status)
