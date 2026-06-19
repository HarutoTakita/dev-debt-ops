"""In-memory ``BlobClient`` for local dev / tests (no GCP).

Concrete ``GcsBlobClient`` implementations (``google-cloud-storage``) live in the
members (``api`` / ``service``) because ``shared`` must stay dependency-light
(``pydantic`` + ``sqlmodel`` only). This mock keeps payloads in a process-local dict,
so api's ``enqueue_job`` spill and the in-process mock-worker resolve the same bytes.
Ported from the mock half of ``app_ref/services/api/app/services`` blob/queue clients.
"""

from shared.gcs import parse_gcs_url


class MockBlobClient:
    """In-memory blob store keyed by ``gs://bucket/object_path``."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def upload(self, bucket: str, object_path: str, data: bytes, content_type: str = "application/json") -> str:
        """Store ``data`` and return its ``gs://`` URL."""
        url = f"gs://{bucket}/{object_path}"
        self._store[url] = data
        return url

    async def download_from_url(self, gcs_url: str) -> bytes:
        """Return the bytes previously uploaded for ``gcs_url``."""
        parse_gcs_url(gcs_url)  # validate scheme
        if gcs_url not in self._store:
            raise FileNotFoundError(gcs_url)
        return self._store[gcs_url]

    async def exists(self, bucket: str, object_path: str) -> bool:
        """Return whether the object exists in the in-memory store."""
        return f"gs://{bucket}/{object_path}" in self._store

    async def delete(self, bucket: str, object_path: str) -> None:
        """Remove the object if present."""
        self._store.pop(f"gs://{bucket}/{object_path}", None)
