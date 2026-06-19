"""``GcsBlobClient`` for the service container (resolves spilled ``$requestRef`` blobs).

``google-cloud-storage`` is imported lazily so importing this module / running the
mock-path tests never needs GCS credentials. Mirrors api's client (separate deploy unit).
"""

import asyncio
import contextlib

from shared.gcs import parse_gcs_url


class GcsBlobClient:
    """Blob client backed by Google Cloud Storage."""

    def __init__(self, project: str | None = None) -> None:
        self._project = project
        self._client = None  # lazily created google.cloud.storage.Client

    def _get_client(self):
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client(project=self._project) if self._project else storage.Client()
        return self._client

    async def upload(self, bucket: str, object_path: str, data: bytes, content_type: str = "application/json") -> str:
        """Upload ``data`` to ``gs://bucket/object_path`` and return that URL."""

        def _upload() -> None:
            self._get_client().bucket(bucket).blob(object_path).upload_from_string(data, content_type=content_type)

        await asyncio.to_thread(_upload)
        return f"gs://{bucket}/{object_path}"

    async def download_from_url(self, gcs_url: str) -> bytes:
        """Download the bytes at a ``gs://`` URL."""
        bucket, object_path = parse_gcs_url(gcs_url)

        def _download() -> bytes:
            return self._get_client().bucket(bucket).blob(object_path).download_as_bytes()

        return await asyncio.to_thread(_download)

    async def exists(self, bucket: str, object_path: str) -> bool:
        """Return whether ``gs://bucket/object_path`` exists."""
        return await asyncio.to_thread(lambda: self._get_client().bucket(bucket).blob(object_path).exists())

    async def delete(self, bucket: str, object_path: str) -> None:
        """Delete ``gs://bucket/object_path`` (best-effort)."""

        def _delete() -> None:
            self._get_client().bucket(bucket).blob(object_path).delete()

        with contextlib.suppress(Exception):
            await asyncio.to_thread(_delete)
