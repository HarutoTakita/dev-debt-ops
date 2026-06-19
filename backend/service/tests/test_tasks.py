"""Tests for the service ``POST /tasks/{pipeline}`` handler (DB write + idempotency)."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.enums import JobStatus, JobType
from shared.models import Job


async def _seed_job(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    job_type: JobType = JobType.ECHO,
    status: JobStatus = JobStatus.QUEUED,
    result_data: dict | None = None,
) -> uuid.UUID:
    async with session_maker() as session:
        job = Job(job_type=job_type, status=status, payload={}, result_data=result_data)
        session.add(job)
        await session.commit()
        return job.id


async def _get_job(session_maker: async_sessionmaker[AsyncSession], job_id: uuid.UUID) -> Job:
    async with session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        return job


async def test_completes_job_and_writes_result(
    client: AsyncClient, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    job_id = await _seed_job(session_maker)
    resp = await client.post("/tasks/echo", json={"jobId": str(job_id), "jobType": "echo", "message": "hi"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"

    job = await _get_job(session_maker, job_id)
    assert job.status == JobStatus.COMPLETED
    assert job.result_data is not None
    assert job.result_data["echoed"] == "hi"
    assert job.completed_at is not None


async def test_idempotent_skip_when_already_completed(
    client: AsyncClient, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    job_id = await _seed_job(session_maker, status=JobStatus.COMPLETED, result_data={"echoed": "original"})
    resp = await client.post("/tasks/echo", json={"jobId": str(job_id), "jobType": "echo", "message": "redelivered"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"

    # Redelivery did not re-run the pipeline — the original result is intact.
    job = await _get_job(session_maker, job_id)
    assert job.result_data == {"echoed": "original"}


async def test_permanent_failure_marks_failed_and_acks(
    client: AsyncClient, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    job_id = await _seed_job(session_maker)
    # Missing required "message" → EchoRequest validation fails → permanent failure.
    resp = await client.post("/tasks/echo", json={"jobId": str(job_id), "jobType": "echo"})
    assert resp.status_code == 200  # acked so Cloud Tasks does not retry
    assert resp.json()["status"] == "FAILED"

    job = await _get_job(session_maker, job_id)
    assert job.status == JobStatus.FAILED
    assert job.error


async def test_unknown_pipeline_returns_404(client: AsyncClient) -> None:
    resp = await client.post("/tasks/nope", json={"jobId": str(uuid.uuid4())})
    assert resp.status_code == 404


async def test_ping_pipeline(client: AsyncClient, session_maker: async_sessionmaker[AsyncSession]) -> None:
    job_id = await _seed_job(session_maker, job_type=JobType.PING)
    resp = await client.post("/tasks/ping", json={"jobId": str(job_id), "jobType": "ping"})
    assert resp.status_code == 200
    job = await _get_job(session_maker, job_id)
    assert job.status == JobStatus.COMPLETED
    assert job.result_data is not None
    assert job.result_data["pong"] is True
