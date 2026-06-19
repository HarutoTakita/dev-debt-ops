"""GCS URL helpers (``gs://bucket/object/path``).

Ported from ``app_ref/services/shared/shared/blob.py`` (``parse_blob_url`` for the
``blob://`` scheme) to the GCS ``gs://`` scheme.
"""


def parse_gcs_url(url: str) -> tuple[str, str]:
    """Split ``gs://bucket/object/path`` into ``(bucket, object/path)``.

    Raises:
        ValueError: If ``url`` is not a ``gs://`` URL or has no object path.
    """
    if not url.startswith("gs://"):
        raise ValueError(f"Not a gs:// URL: {url}")
    rest = url[len("gs://") :]
    slash = rest.find("/")
    if slash <= 0:
        raise ValueError(f"Invalid gs:// URL (missing object path): {url}")
    return rest[:slash], rest[slash + 1 :]
