"""Job polling API — the frontend polls ``GET /api/v1/jobs/{id}`` until COMPLETED.

The service (or the local mock-worker) writes the Job's terminal state directly to the
DB; this endpoint just reads the latest row. Access is scoped to the job's creator.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.api.deps import CurrentUser, SessionDep
from app.core.exceptions import NotFoundError
from app.schemas.job import JobRead
from shared.models import Job

router = APIRouter(tags=["jobs"])


@router.get(
    "/jobs/{job_id}",
    response_model=JobRead,
    summary="Get a job's status / result",
    response_description="The job's latest state; poll until status is COMPLETED / FAILED.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_404_NOT_FOUND: {"description": "Job not found or not owned by the caller."},
    },
)
async def get_job(
    job_id: Annotated[uuid.UUID, Path(description="Job id returned at enqueue time.")],
    current_user: CurrentUser,
    session: SessionDep,
) -> Job:
    """Return the job by id, scoped to its creator.

    Raises:
        NotFoundError: If the job does not exist or was created by another user.
    """
    job = await session.get(Job, job_id)
    if job is None or job.created_by != current_user.id:
        raise NotFoundError("Job not found")
    return job
