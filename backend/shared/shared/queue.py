"""Queue / blob-store client Protocols.

These define the contract ``api`` uses to dispatch work to ``service`` (Cloud Tasks)
and to spill large payloads (Cloud Storage). Concrete implementations live in the
members (``api`` / ``service``) and the in-memory mock lives in ``shared.blob``;
this module fixes the shapes so both containers agree on them.

Ported from ``app_ref/services/api/app/services/interfaces.py`` (``QueueClient`` /
``BlobClient``). The Azure ``send/receive/delete`` queue verbs collapse to a single
``dispatch`` because Cloud Tasks is push-based (point-to-point HTTP), so ``service``
never polls. result is not a queue at all — ``service`` writes the ``Job`` row directly.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TaskDispatcher(Protocol):
    """Dispatch a unit of work to the ``service`` container's ``/tasks/{pipeline}``."""

    async def dispatch(self, pipeline: str, payload: dict[str, Any], *, dedup_key: str | None = None) -> None:
        """Create a Cloud Tasks HTTP task targeting ``service``'s ``/tasks/{pipeline}``.

        ``dedup_key`` names the task so at-least-once retries collapse to one task.
        """
        ...


@runtime_checkable
class BlobClient(Protocol):
    """Spill / fetch payloads that exceed the queue message size (GCS in production)."""

    async def upload(self, bucket: str, object_path: str, data: bytes, content_type: str = "application/json") -> str:
        """Upload ``data`` to ``gs://bucket/object_path`` and return that ``gs://`` URL."""
        ...

    async def download_from_url(self, gcs_url: str) -> bytes:
        """Resolve a ``gs://`` URL and return its bytes."""
        ...

    async def exists(self, bucket: str, object_path: str) -> bool:
        """Return whether ``gs://bucket/object_path`` exists."""
        ...

    async def delete(self, bucket: str, object_path: str) -> None:
        """Delete ``gs://bucket/object_path`` (no error if absent)."""
        ...
