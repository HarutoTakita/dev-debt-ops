"""``LocalHttpDispatcher`` — dispatch tasks straight to the ``service`` container over HTTP.

Local-dev bridge between the in-process mock path and real Cloud Tasks. The in-process
mock-worker can only run ``shared`` pipelines (``echo`` / ``ping``) because ``api`` cannot
import ``service``-only pipelines (``stack_analysis``). With a real ``service`` container
running (``docker compose``), this dispatcher POSTs to ``{SERVICE_TASKS_URL}/tasks/{pipeline}``
exactly like Cloud Tasks would — minus the OIDC token (the service skips OIDC verification
when ``USE_MOCK_QUEUE`` is true). The POST is fire-and-forget so ``analyze-stack`` still
returns ``202`` immediately; the service processes the job and writes the ``Job`` row
directly, and the frontend polls ``GET /jobs/{id}`` (issue 018).
"""

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Heavy pipelines (stack analysis) can run for tens of seconds; allow generous time.
_DISPATCH_TIMEOUT_SECONDS = 600.0

# Hold strong references to in-flight fire-and-forget tasks so they are not GC'd mid-flight.
_background_tasks: set[asyncio.Task] = set()


class LocalHttpDispatcher:
    """Local HTTP implementation of the ``TaskDispatcher`` Protocol (no Cloud Tasks/OIDC)."""

    def __init__(self, service_url: str) -> None:
        self._service_url = service_url.rstrip("/")

    async def dispatch(self, pipeline: str, payload: dict[str, Any], *, dedup_key: str | None = None) -> None:
        """Fire-and-forget POST to the service's ``/tasks/{pipeline}`` endpoint.

        ``dedup_key`` is ignored — the service enforces idempotency via the ``Job`` status
        in ``shared.worker.run_task`` (Cloud Tasks at-least-once semantics are emulated).
        """
        del dedup_key
        url = f"{self._service_url}/tasks/{pipeline}"

        async def _post() -> None:
            try:
                async with httpx.AsyncClient(timeout=_DISPATCH_TIMEOUT_SECONDS) as client:
                    resp = await client.post(url, json=payload)
                if resp.status_code >= 400:
                    logger.warning("local_dispatch_non_2xx pipeline=%s status=%s", pipeline, resp.status_code)
            except Exception:
                logger.exception("local_dispatch_failed pipeline=%s url=%s", pipeline, url)

        # Detached so enqueue_job returns immediately and analyze-stack answers 202.
        task = asyncio.create_task(_post())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    @classmethod
    def from_settings(cls) -> "LocalHttpDispatcher":
        """Build a dispatcher targeting ``settings.SERVICE_TASKS_URL``."""
        return cls(settings.SERVICE_TASKS_URL)
