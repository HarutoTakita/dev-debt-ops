"""Service configuration read from environment variables.

The service avoids ``pydantic-settings`` (not a service dependency); it reads the few env
vars it needs directly. Names match api's ``Settings`` and issue-017's Cloud Run injection.
Values are read at call time so tests can set them via ``monkeypatch.setenv``.
"""

import os


def environment() -> str:
    """Deployment environment (``dev`` / ``stg`` / ``prod``). Mirrors api's ``ENVIRONMENT``."""
    return os.environ.get("ENVIRONMENT", "dev").lower()


def use_mock_queue() -> bool:
    """Whether to skip Cloud Tasks OIDC verification (local dev / tests).

    Defaults to ``false`` (fail-closed): the worker endpoint runs pipelines and writes Job /
    domain rows directly to Cloud SQL, so OIDC verification must be on unless dev explicitly
    opts out. Dev enables it via ``.env.dev`` (``USE_MOCK_QUEUE=true``); tests set it in conftest.
    """
    return os.environ.get("USE_MOCK_QUEUE", "false").lower() == "true"


def validate_runtime_config() -> None:
    """Fail-closed guard: the mock queue (OIDC bypass) must never be enabled outside dev.

    Called at app startup. In ``stg`` / ``prod`` an enabled mock queue would leave
    ``POST /tasks/{pipeline}`` unauthenticated, so we refuse to start.
    """
    if environment() != "dev" and use_mock_queue():
        raise RuntimeError(
            "USE_MOCK_QUEUE must be false outside dev — it disables Cloud Tasks OIDC verification "
            "on the worker endpoint. Set USE_MOCK_QUEUE=false (or unset it) in non-dev environments."
        )


def service_tasks_url() -> str:
    """This service's public base URL — the expected OIDC token audience."""
    return os.environ.get("SERVICE_TASKS_URL", "http://localhost:8001")


def tasks_invoker_sa() -> str:
    """The service account Cloud Tasks uses to mint the OIDC token (expected token email)."""
    return os.environ.get("TASKS_INVOKER_SA", "")


def google_cloud_project() -> str:
    """GCP project id (for the GCS client / Vertex AI)."""
    return os.environ.get("GOOGLE_CLOUD_PROJECT", "")


def google_cloud_location() -> str:
    """GCP region for Vertex AI (aligned with the queue/infra region, issue 016/017/018)."""
    return os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-northeast1")


def gemini_model() -> str:
    """Gemini model id used by the stack-analysis agent."""
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def gemini_timeout_ms() -> int:
    """Client-side timeout (in milliseconds) for Gemini ``generate_content`` calls.

    Without a timeout a stalled Vertex response blocks the worker indefinitely, leaving the
    Job stuck in ``PROCESSING`` until the 1h stale-job reaper. Bounding the call makes it raise
    (``httpx`` timeout → the ``_generate`` retry, or otherwise the worker's FAILED path) instead
    of hanging forever. Generous by default since clustering prompts can be large.
    """
    return int(os.environ.get("GEMINI_TIMEOUT_MS", "120000"))


def github_app_id() -> str:
    """GitHub App numeric id (method B: service mints installation tokens)."""
    return os.environ.get("GITHUB_APP_ID", "")


def github_app_private_key() -> str:
    """GitHub App RSA private key (PEM) — sourced from Secret Manager in production."""
    return os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
