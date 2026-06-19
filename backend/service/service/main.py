"""Service FastAPI app — heavy-processing worker.

In production this runs as an internal Cloud Run service invoked by Cloud Tasks at
``POST /tasks/{pipeline}`` (OIDC-authenticated). In this issue the task endpoint is a
**stub**: it logs the received payload and returns ``202 Accepted``. Real pipeline
dispatch, OIDC verification, ``$requestRef`` resolution and Job result writes (via
``service.db`` against ``shared.models.Job``) are implemented in issue 016 / 018.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="Rosetta Service", summary="Heavy-processing worker (async pipelines)")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe (Cloud Run / compose healthcheck)."""
    return {"status": "ok"}


@app.post("/tasks/{pipeline}", status_code=202)
async def run_task(pipeline: str, request: Request) -> JSONResponse:
    """Cloud Tasks HTTP target (STUB).

    Implemented in issue 016 / 018:
    1. verify the OIDC token from Cloud Tasks,
    2. resolve a ``$requestRef`` from GCS if the payload was spilled,
    3. run the ``shared.enums.JobType`` pipeline registered under ``pipelines/``,
    4. update ``shared.models.Job`` to ``COMPLETED`` / ``FAILED`` + ``result_data`` via
       ``service.db`` (no callback to api — the frontend polls ``GET /api/v1/jobs/{id}``);
       idempotent: skip if the Job is already ``COMPLETED``.

    For now it logs the receipt and returns ``202 Accepted``.
    """
    body = await request.body()
    logger.info("task_received pipeline=%s bytes=%d", pipeline, len(body))
    return JSONResponse(status_code=202, content={"accepted": True, "pipeline": pipeline})
