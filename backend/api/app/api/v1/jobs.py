"""Job polling API — the frontend polls ``GET /api/v1/jobs/{id}`` until COMPLETED.

The service (or the local mock-worker) writes the Job's terminal state directly to the
DB; this endpoint just reads the latest row. Access is scoped to the job's creator. For
``stack_analysis`` jobs it also lifts ``agent_trace`` out of ``result_data`` and attaches the
persisted ``TechStack`` so the frontend gets progress + result in one response.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.core.exceptions import NotFoundError
from app.schemas.job import JobRead
from shared.enums import JobType
from shared.models import Job, TechStack

router = APIRouter(tags=["jobs"])


async def _stack_tech_stack(session: SessionDep, payload: dict) -> dict | None:
    """Load the persisted ``TechStack`` for a stack_analysis job's (owner, repo)."""
    owner, repo = payload.get("owner"), payload.get("repo")
    if not owner or not repo:
        return None
    result = await session.exec(
        select(TechStack).where(
            TechStack.owner == owner,
            TechStack.repo == repo,
        )
    )
    row = result.first()
    if row is None:
        return None
    return {
        "owner": row.owner,
        "repo": row.repo,
        "analyzed_at": row.analyzed_at,
        "languages": row.languages or [],
        "categories": row.categories or {},
    }


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
) -> JobRead:
    """Return the job by id, scoped to its creator.

    Raises:
        NotFoundError: If the job does not exist or was created by another user.
    """
    job = await session.get(Job, job_id)
    if job is None or job.created_by != current_user.id:
        raise NotFoundError("Job not found")

    read = JobRead.model_validate(job)
    if job.job_type == JobType.STACK_ANALYSIS:
        # result_data is written by the service with camelCase aliases (agentTrace).
        read.agent_trace = (job.result_data or {}).get("agentTrace", [])
        if read.status == "COMPLETED":
            read.tech_stack = await _stack_tech_stack(session, job.payload or {})
    return read
