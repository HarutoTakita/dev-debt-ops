"""Service configuration read from environment variables.

The service avoids ``pydantic-settings`` (not a service dependency); it reads the few env
vars it needs directly. Names match api's ``Settings`` and issue-017's Cloud Run injection.
Values are read at call time so tests can set them via ``monkeypatch.setenv``.
"""

import os


def use_mock_queue() -> bool:
    """Whether to skip Cloud Tasks OIDC verification (local dev / tests)."""
    return os.environ.get("USE_MOCK_QUEUE", "true").lower() == "true"


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


def github_app_id() -> str:
    """GitHub App numeric id (method B: service mints installation tokens)."""
    return os.environ.get("GITHUB_APP_ID", "")


def github_app_private_key() -> str:
    """GitHub App RSA private key (PEM) — sourced from Secret Manager in production."""
    return os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
