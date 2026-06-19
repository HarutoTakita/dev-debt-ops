"""KC (Knowledge Coverage) API — analysis trigger (issue 029).

``POST .../analyze-kc`` is async (issue 018 pattern): it resolves the caller's GitHub App
installation id and enqueues a ``kc_analysis`` Job for the project's repository, returning
``202`` immediately — the authorship/blame + dependency analysis runs in the ``service``
container off the request path. The frontend polls ``GET /jobs/{id}``.

The route is project-scoped (``/orgs/{slug}/projects/{project_slug}/...``, consistent with issue
028's ``detect-debts``) because the pipeline needs ``project_id`` as its analysis scope. The KC
**delivery** (``GET .../galaxy``) is owned by issue 032; this module only owns the trigger.
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

router = APIRouter(tags=["kc"])


@router.post(
    "/orgs/{slug}/projects/{project_slug}/analyze-kc",
    response_model=JobEnqueuedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Knowledge Coverage 算出を非同期ジョブとして enqueue する",
)
async def analyze_kc(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    installation_id: InstallationIdDep,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    session: SessionDep,
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
) -> JobEnqueuedOut:
    """Enqueue a ``kc_analysis`` job for the project's repository and return ``202``.

    Method B keeps the GitHub secret off the queue (only ``installation_id`` travels). The
    service computes KC(file,dev) / KC(file) + wormholes and persists ``file_kc`` / ``dependencies``.
    """
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
