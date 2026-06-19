"""End-to-end: enqueue an echo job, let the mock-worker process it, poll GET /jobs/{id}."""

import uuid

import pytest
from httpx import AsyncClient

from app.core import db as app_db
from app.services.dependencies import (
    get_blob_client,
    get_task_dispatcher,
    reset_blob_client,
    reset_task_dispatcher,
)
from app.services.job_orchestrator import enqueue_job
from app.services.mock_worker import run_once
from shared.enums import JobType


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Isolate the process-singleton mock dispatcher / blob between tests."""
    reset_task_dispatcher()
    reset_blob_client()
    yield
    reset_task_dispatcher()
    reset_blob_client()


async def test_echo_job_runs_to_completion(authenticated_client: AsyncClient) -> None:
    me = (await authenticated_client.get("/api/v1/users/me")).json()
    user_id = uuid.UUID(me["id"])

    dispatcher = get_task_dispatcher()
    blob = get_blob_client()
    async with app_db.async_session_maker() as session:
        job = await enqueue_job(
            session=session,
            dispatcher=dispatcher,
            blob_client=blob,
            job_type=JobType.ECHO,
            payload={"message": "hello"},
            created_by=user_id,
        )

    # Right after enqueue the job is QUEUED.
    queued = await authenticated_client.get(f"/api/v1/jobs/{job.id}")
    assert queued.status_code == 200
    assert queued.json()["status"] == "QUEUED"

    # The mock-worker (standing in for the service) processes the queued task.
    assert await run_once() == 1

    done = await authenticated_client.get(f"/api/v1/jobs/{job.id}")
    body = done.json()
    assert body["status"] == "COMPLETED"
    assert body["result_data"]["echoed"] == "hello"
    assert body["error"] is None


async def test_job_not_owned_returns_404(authenticated_client: AsyncClient) -> None:
    # A job created by nobody (created_by=None) is not visible to the caller.
    dispatcher = get_task_dispatcher()
    blob = get_blob_client()
    async with app_db.async_session_maker() as session:
        job = await enqueue_job(
            session=session,
            dispatcher=dispatcher,
            blob_client=blob,
            job_type=JobType.PING,
            payload={},
        )
    resp = await authenticated_client.get(f"/api/v1/jobs/{job.id}")
    assert resp.status_code == 404
