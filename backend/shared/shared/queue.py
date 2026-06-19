"""Queue / blob-store client Protocols (interface placeholders).

These define the contract that api uses to dispatch work to service and to spill
large payloads. Concrete implementations (Cloud Tasks, Cloud Storage) are added in
issue 016; this module only fixes the shapes so both containers agree on them.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class TaskQueue(Protocol):
    """Dispatch a unit of work to the service container (Cloud Tasks in issue 016)."""

    async def enqueue(self, pipeline: str, payload: bytes, *, dedup_key: str | None = None) -> None:
        """Enqueue ``payload`` for ``pipeline``; ``dedup_key`` de-duplicates retries."""
        ...


@runtime_checkable
class BlobStore(Protocol):
    """Spill / fetch large payloads that exceed the queue message size (GCS in issue 016)."""

    async def put(self, key: str, data: bytes) -> str:
        """Store ``data`` under ``key`` and return a reference (e.g. ``gs://...``)."""
        ...

    async def get(self, ref: str) -> bytes:
        """Fetch the bytes previously stored under reference ``ref``."""
        ...
