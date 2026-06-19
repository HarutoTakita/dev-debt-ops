"""Task-queue / blob dependency factories with mock ↔ real switching.

Ported from ``app_ref/services/api/app/services/dependencies.py``
(``get_queue_client`` / ``is_mock_queue`` / ``get_blob_client``). The mock dispatcher
and mock blob are process-singletons so that ``enqueue_job`` and the in-process
mock-worker share the same in-memory queue and blob store.
"""

from app.core.config import settings
from app.services.mock_task_dispatcher import MockTaskDispatcher
from shared.blob import MockBlobClient
from shared.queue import BlobClient, TaskDispatcher

_mock_dispatcher: MockTaskDispatcher | None = None
_mock_blob: MockBlobClient | None = None


def get_task_dispatcher() -> TaskDispatcher:
    """Return the in-memory dispatcher (mock mode) or a Cloud Tasks dispatcher."""
    global _mock_dispatcher
    if settings.use_mock_queue():
        if _mock_dispatcher is None:
            _mock_dispatcher = MockTaskDispatcher()
        return _mock_dispatcher
    from app.services.cloud_tasks_dispatcher import CloudTasksDispatcher

    return CloudTasksDispatcher.from_settings()


def get_mock_dispatcher() -> MockTaskDispatcher:
    """Return the singleton mock dispatcher, creating it if needed (mock mode only)."""
    global _mock_dispatcher
    if _mock_dispatcher is None:
        _mock_dispatcher = MockTaskDispatcher()
    return _mock_dispatcher


def get_blob_client() -> BlobClient:
    """Return the in-memory blob (mock mode) or a GCS blob client."""
    global _mock_blob
    if settings.use_mock_blob():
        if _mock_blob is None:
            _mock_blob = MockBlobClient()
        return _mock_blob
    from app.services.gcs_blob_client import GcsBlobClient

    return GcsBlobClient(project=settings.GOOGLE_CLOUD_PROJECT or None)


def reset_task_dispatcher() -> None:
    """Drop the cached mock dispatcher (tests)."""
    global _mock_dispatcher
    _mock_dispatcher = None


def reset_blob_client() -> None:
    """Drop the cached mock blob (tests)."""
    global _mock_blob
    _mock_blob = None
