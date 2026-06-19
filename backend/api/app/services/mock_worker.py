"""In-process mock-worker — stands in for the ``service`` container in local dev / tests.

Drains the ``MockTaskDispatcher`` and runs each task through ``shared.worker.run_task``,
writing the ``Job`` row exactly as the real ``service`` would (no callback to api — the
frontend polls ``GET /api/v1/jobs/{id}``). Ported from
``app_ref/services/api/app/services/mock_worker.py`` (background loop), minus the result
publisher. Only started when ``settings.use_mock_worker()`` is true (never in production).
"""

import asyncio
import logging

from app.core import db as app_db
from app.services.dependencies import get_blob_client, get_mock_dispatcher
from shared.worker import TransientTaskError, run_task

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.2


async def run_once() -> int:
    """Drain all pending mock tasks once, persisting each Job. Returns tasks processed."""
    dispatcher = get_mock_dispatcher()
    blob_client = get_blob_client()
    pending = dispatcher.pop_all()
    for task in pending:
        try:
            async with app_db.async_session_maker() as session:
                await run_task(session, pipeline=task.pipeline, request_body=task.payload, blob_client=blob_client)
        except TransientTaskError:
            logger.warning("mock_worker_transient_error pipeline=%s", task.pipeline, exc_info=True)
        except Exception:
            logger.exception("mock_worker_failed pipeline=%s", task.pipeline)
    return len(pending)


async def run_mock_worker() -> None:
    """Background loop: poll the mock dispatcher and process tasks until cancelled."""
    logger.info("mock_worker_started")
    try:
        while True:
            processed = await run_once()
            if processed == 0:
                await asyncio.sleep(_POLL_INTERVAL)
    except asyncio.CancelledError:
        logger.info("mock_worker_stopped")
        raise
