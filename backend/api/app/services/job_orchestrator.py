"""Job orchestration — enqueue (persist + spill + dispatch) and stale-job cleanup.

``enqueue_job`` is the high-level entry the API routes call (issue-018's analyze-stack
route, and the echo end-to-end test): it persists a ``Job`` as ``QUEUED``, spills the
request to GCS when it exceeds the Cloud Tasks body limit, then dispatches the task.
Ported from ``app_ref/services/api/app/services/workflow_orchestrator.py`` (``enqueue_job``)
and ``result_poller._timeout_stale_jobs``.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import update
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from shared.enums import JobStatus, JobType
from shared.models import Job
from shared.queue import BlobClient, TaskDispatcher

# Cloud Tasks caps the HTTP body at ~100KB; stay safely below it before spilling to GCS.
_MAX_TASK_REQUEST_BYTES = 90_000
_REQUEST_BLOB_PREFIX = "requests"


async def enqueue_job(
    *,
    session: AsyncSession,
    dispatcher: TaskDispatcher,
    blob_client: BlobClient,
    job_type: JobType,
    payload: dict[str, Any],
    created_by: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> Job:
    """Persist a ``QUEUED`` Job, spill the request if oversized, then dispatch the task.

    The full domain ``payload`` is stored on the Job; only the *queue message* spills to
    GCS when it exceeds ``_MAX_TASK_REQUEST_BYTES`` — in which case the persisted
    ``Job.payload`` is replaced with the ``{"$requestRef": "gs://..."}`` reference too.
    """
    job = Job(
        job_type=job_type,
        status=JobStatus.QUEUED,
        payload=payload,
        created_by=created_by,
        project_id=project_id,
    )
    session.add(job)
    await session.flush()  # assign job.id before building the request

    request: dict[str, Any] = {"jobId": str(job.id), "jobType": job_type.value, **payload}
    if len(json.dumps(request).encode()) > _MAX_TASK_REQUEST_BYTES:
        object_path = f"{_REQUEST_BLOB_PREFIX}/{job_type.value}/{job.id}.json"
        gcs_url = await blob_client.upload(settings.JOB_PAYLOAD_BUCKET, object_path, json.dumps(request).encode())
        request = {"jobId": str(job.id), "jobType": job_type.value, "$requestRef": gcs_url}
        job.payload = {"$requestRef": gcs_url}
        session.add(job)

    await session.commit()
    await dispatcher.dispatch(job_type.value, request, dedup_key=str(job.id))
    return job


async def timeout_stale_jobs(session: AsyncSession, *, max_age: timedelta = timedelta(hours=1)) -> list[uuid.UUID]:
    """Fail ``PROCESSING`` jobs whose ``started_at`` is older than ``max_age``.

    Result is written directly by the service; a job stuck in ``PROCESSING`` means the
    service crashed mid-task (Cloud Tasks retries exhausted), so api reaps it to ``FAILED``.
    Returns the ids that were timed out.
    """
    now = datetime.now(UTC)
    cutoff = now - max_age
    result = await session.exec(
        update(Job)
        .where(
            col(Job.status) == JobStatus.PROCESSING,
            col(Job.started_at).is_not(None),
            col(Job.started_at) < cutoff,
        )
        .values(status=JobStatus.FAILED, error="Job timed out", completed_at=now)
        .returning(col(Job.id))
    )
    timed_out = [row[0] for row in result.all()]
    await session.commit()
    return timed_out
