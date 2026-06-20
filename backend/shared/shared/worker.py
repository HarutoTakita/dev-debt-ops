"""Core task processing shared by api's mock-worker and service's HTTP handler.

Both run the *same* logic: resolve a spilled ``$requestRef`` from GCS, enforce
idempotency (skip an already-``COMPLETED`` Job), mark ``PROCESSING``, run the pipeline
``process`` fn, then write the ``Job`` row to ``COMPLETED`` / ``FAILED``. It lives in
``shared`` because ``api`` cannot import ``service`` (only ``shared`` is installed).

Ported from ``app_ref/services/worker/worker/main.py`` (``_poll_queue`` body +
``_resolve_request_ref``) and ``result_poller._persist_job_status`` — collapsed into a
single direct-DB-write path (no result queue, no api callback).
"""

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import JobStatus
from shared.models import Job
from shared.pipelines.context import PipelineContext
from shared.queue import BlobClient
from shared.registry import PIPELINES, Pipeline


class TransientTaskError(Exception):
    """Raised for transient infra failures so the caller can retry (HTTP 5xx)."""


async def run_task(
    session: AsyncSession,
    *,
    pipeline: str,
    request_body: dict[str, Any],
    blob_client: BlobClient | None = None,
    pipelines: Mapping[str, Pipeline] | None = None,
) -> Job:
    """Process one task and persist its Job row. Returns the (updated) Job.

    Idempotent: if the Job is already ``COMPLETED`` it is returned untouched. A pipeline
    (validation / domain) failure marks the Job ``FAILED`` and returns normally — the
    caller acks it. Infra failures (unknown pipeline, missing Job, blob/DB errors) raise
    so the caller can surface a retryable error.

    ``pipelines`` selects the registry to resolve ``pipeline`` against; it defaults to the
    ``shared`` registry (echo / ping) used by api's mock-worker, while the ``service``
    container passes its own registry that adds heavy pipelines (e.g. ``stack-analysis``).

    Raises:
        TransientTaskError: If the Job id is missing/unknown or the pipeline is unknown.
    """
    registry = pipelines if pipelines is not None else PIPELINES
    job_id_raw = request_body.get("jobId")
    if not job_id_raw:
        raise TransientTaskError("request missing jobId")
    job_pk = uuid.UUID(str(job_id_raw))
    job = await session.get(Job, job_pk)
    if job is None:
        raise TransientTaskError(f"job not found: {job_id_raw}")

    # Idempotency: Cloud Tasks is at-least-once; a redelivered, already-finished job is a no-op.
    if job.status == JobStatus.COMPLETED:
        return job

    if pipeline not in registry:
        raise TransientTaskError(f"unknown pipeline: {pipeline}")
    request_model, _result_model, process_fn = registry[pipeline]

    # Resolve a spilled request before marking PROCESSING (a download failure is transient).
    body = request_body
    if "$requestRef" in body:
        if blob_client is None:
            raise TransientTaskError("request spilled to GCS but no blob client available")
        body = json.loads(await blob_client.download_from_url(body["$requestRef"]))

    job.status = JobStatus.PROCESSING
    job.started_at = datetime.now(UTC)
    session.add(job)
    await session.commit()

    # The pipeline persists its domain rows on this same session WITHOUT committing
    # (it flushes for ids). run_task owns the single terminal commit, so domain rows and the
    # Job's terminal status land atomically — a failure leaves neither behind (issue-042).
    try:
        request = request_model.model_validate(body)
        ctx = PipelineContext(blob=blob_client, session=session)
        result = await process_fn(request, ctx)
    except TransientTaskError:
        # Transient (e.g. GitHub rate limit) — discard partial work and let the caller retry
        # (HTTP 503 → Cloud Tasks redelivery). Do NOT mark the Job FAILED (issue-045).
        await session.rollback()
        raise
    except Exception as exc:
        # Discard any domain rows the pipeline flushed before failing, then mark FAILED. Without
        # the rollback those pending rows would be committed alongside the FAILED Job below.
        await session.rollback()
        # rollback() expired `job`; re-fetch by the known PK. Reading `job.id` here would
        # trigger a sync lazy-load of the expired attribute outside the async greenlet
        # (sqlalchemy.exc.MissingGreenlet), masking the real pipeline error as an HTTP 503.
        job = await session.get(Job, job_pk)
        if job is None:  # pragma: no cover - the PROCESSING row was committed above
            raise TransientTaskError(f"job vanished mid-processing: {job_id_raw}") from exc
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.completed_at = datetime.now(UTC)
        session.add(job)
        await session.commit()
        return job

    job.status = JobStatus.COMPLETED
    job.result_data = result.model_dump(by_alias=True)
    job.completed_at = datetime.now(UTC)
    session.add(job)
    await session.commit()
    return job
