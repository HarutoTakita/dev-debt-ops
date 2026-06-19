"""``MockTaskDispatcher`` — in-memory stand-in for Cloud Tasks (local dev / tests).

Ported from ``app_ref/services/api/app/services/mock_queue_client.py``. ``dispatch``
appends ``(pipeline, payload)`` to an internal list; the in-process mock-worker
(``app.services.mock_worker``) drains it. ``dedup_key`` collapses duplicate dispatches
the way a Cloud Tasks ``task.name`` would.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingTask:
    """A task queued in the mock dispatcher, awaiting the mock-worker."""

    pipeline: str
    payload: dict[str, Any]
    dedup_key: str | None = None


@dataclass
class MockTaskDispatcher:
    """Collects dispatched tasks in memory; the mock-worker pops and runs them."""

    tasks: list[PendingTask] = field(default_factory=list)
    _seen_dedup_keys: set[str] = field(default_factory=set)

    async def dispatch(self, pipeline: str, payload: dict[str, Any], *, dedup_key: str | None = None) -> None:
        """Append a task; skip if ``dedup_key`` was already dispatched (idempotent)."""
        if dedup_key is not None:
            if dedup_key in self._seen_dedup_keys:
                return
            self._seen_dedup_keys.add(dedup_key)
        self.tasks.append(PendingTask(pipeline=pipeline, payload=payload, dedup_key=dedup_key))

    def pop_all(self) -> list[PendingTask]:
        """Remove and return all pending tasks (the mock-worker drains the queue)."""
        pending = self.tasks
        self.tasks = []
        return pending
