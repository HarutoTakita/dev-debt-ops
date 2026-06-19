"""enqueue_job spills oversized requests to (mock) GCS, leaving only a $requestRef."""

import pytest
from httpx import AsyncClient

from app.core import db as app_db
from app.core.config import settings
from app.services.dependencies import (
    get_blob_client,
    get_task_dispatcher,
    reset_blob_client,
    reset_task_dispatcher,
)
from app.services.job_orchestrator import enqueue_job
from shared.enums import JobType
from shared.models import Job


@pytest.fixture(autouse=True)
def _reset_singletons():
    reset_task_dispatcher()
    reset_blob_client()
    yield
    reset_task_dispatcher()
    reset_blob_client()


async def test_large_payload_spills_to_blob(authenticated_client: AsyncClient) -> None:
    settings.JOB_PAYLOAD_BUCKET = "test-job-payloads"
    dispatcher = get_task_dispatcher()
    blob = get_blob_client()

    big_message = "x" * 100_000  # exceeds _MAX_TASK_REQUEST_BYTES (~90KB)
    async with app_db.async_session_maker() as session:
        job = await enqueue_job(
            session=session,
            dispatcher=dispatcher,
            blob_client=blob,
            job_type=JobType.ECHO,
            payload={"message": big_message},
        )

    # The persisted Job.payload is replaced with the GCS reference.
    async with app_db.async_session_maker() as session:
        refreshed = await session.get(Job, job.id)
        assert refreshed is not None
        assert set(refreshed.payload) == {"$requestRef"}
        assert refreshed.payload["$requestRef"].startswith("gs://test-job-payloads/requests/echo/")

    # The dispatched task carries only the reference, not the big message.
    dispatched = dispatcher.tasks[0].payload
    assert "$requestRef" in dispatched
    assert "message" not in dispatched
