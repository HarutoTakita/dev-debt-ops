"""Service FastAPI app — heavy-processing worker (Cloud Tasks HTTP target).

In production this runs as an internal Cloud Run service invoked by Cloud Tasks at
``POST /tasks/{pipeline}`` (OIDC-authenticated). The handler resolves a spilled
``$requestRef`` from GCS, runs the registered pipeline, and writes the ``Job`` row
directly to Cloud SQL (``COMPLETED`` / ``FAILED`` + ``result_data``) — no callback to api;
the frontend polls ``GET /api/v1/jobs/{id}``. Ported from ``app_ref`` worker ``_poll_queue``
semantics, translated from queue-polling to HTTP push.
"""

import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from service import config
from service.db import get_session
from service.dependencies import get_blob_client, verify_oidc
from service.registry import PIPELINES
from shared.queue import BlobClient
from shared.worker import TransientTaskError, run_task

logger = logging.getLogger(__name__)

# Fail-closed: refuse to start in stg/prod with the OIDC bypass enabled (issue-038).
config.validate_runtime_config()

app = FastAPI(title="DevDebtOps Service", summary="Heavy-processing worker (async pipelines)")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe (Cloud Run / compose healthcheck)."""
    return {"status": "ok"}


@app.post("/tasks/{pipeline}")
async def run_task_endpoint(
    pipeline: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    blob: Annotated[BlobClient, Depends(get_blob_client)],
    _: Annotated[None, Depends(verify_oidc)],
) -> JSONResponse:
    """Cloud Tasks HTTP target — process one task and persist its Job row.

    Returns 2xx (ack) on success and on permanent pipeline failure (``Job=FAILED``);
    returns 503 on transient failures so Cloud Tasks retries (idempotency in
    ``shared.worker.run_task`` prevents double-processing). Unknown pipeline → 404.
    """
    if pipeline not in PIPELINES:
        return JSONResponse(status_code=404, content={"detail": f"unknown pipeline: {pipeline}"})

    body = await request.json()
    try:
        job = await run_task(session, pipeline=pipeline, request_body=body, blob_client=blob, pipelines=PIPELINES)
    except TransientTaskError as exc:
        logger.warning("task_transient_error pipeline=%s detail=%s", pipeline, exc)
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    except Exception:
        logger.exception("task_infra_error pipeline=%s", pipeline)
        return JSONResponse(status_code=503, content={"detail": "transient processing error"})

    # job.status may be a plain str (freshly loaded from the String column) or a JobStatus
    # enum (just set by run_task); str() yields the uppercase value either way.
    return JSONResponse(status_code=200, content={"jobId": str(job.id), "status": str(job.status)})
