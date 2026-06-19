"""Service dependency factories (blob client + OIDC verification)."""

from fastapi import HTTPException, Request

from service import config
from service.gcs_blob_client import GcsBlobClient
from shared.queue import BlobClient


def get_blob_client() -> BlobClient:
    """Return a GCS blob client (overridden with a mock in tests)."""
    return GcsBlobClient(project=config.google_cloud_project() or None)


async def verify_oidc(request: Request) -> None:
    """Verify the Cloud Tasks OIDC bearer token (audience + invoker SA email).

    Skipped entirely when ``USE_MOCK_QUEUE`` is true (local dev / tests). On failure
    raises 401 so Cloud Tasks treats it as a permanent (non-retryable) rejection.
    """
    if config.use_mock_queue():
        return

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth.removeprefix("Bearer ").strip()

    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), audience=config.service_tasks_url())
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid OIDC token") from exc

    expected_sa = config.tasks_invoker_sa()
    if expected_sa and claims.get("email") != expected_sa:
        raise HTTPException(status_code=401, detail="unexpected token principal")
