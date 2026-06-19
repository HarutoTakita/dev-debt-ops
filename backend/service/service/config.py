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
    """GCP project id (for the GCS client)."""
    return os.environ.get("GOOGLE_CLOUD_PROJECT", "")
