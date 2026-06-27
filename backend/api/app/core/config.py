from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables via pydantic-settings.

    All fields map directly to environment variables (or `.env` file entries). Sensitive values
    use `SecretStr` so they are redacted in logs. In non-dev environments,
    `_validate_production_settings` enforces that `SECRET_KEY` has been rotated and
    `COOKIE_SECURE` is enabled.
    """

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@db:5432/app",
        description="Async PostgreSQL DSN used by SQLAlchemy.",
    )

    # Auth
    SECRET_KEY: SecretStr = Field(
        default=SecretStr("change-me-in-production"),
        description="HMAC secret used to sign JWT tokens; must be rotated from the default in non-dev environments.",
    )
    COOKIE_SECURE: bool = Field(
        default=False,
        description="If True, the auth cookie is set with the Secure flag; must be True in non-dev environments.",
    )
    JWT_LIFETIME_SECONDS: int = Field(default=1800, description="Access-token lifetime in seconds (30 min).")
    REFRESH_TOKEN_LIFETIME_SECONDS: int = Field(default=604_800, description="Refresh-token lifetime in seconds (7 d).")

    # Guest demo (issue 069). When true, expose POST /api/v1/auth/demo + the login-screen
    # "お試しはこちら" button so visitors without a GitHub account can browse seeded sample data.
    # Keep false in real production; enable only for the hackathon showcase / stg.
    DEMO_MODE_ENABLED: bool = Field(
        default=False, description="Enable the GitHub-less guest demo login + sample data (issue 069)."
    )

    # AI (Google Gemini via Vertex AI). GOOGLE_CLOUD_LOCATION is shared with Cloud Tasks / GCS
    # (issue 016/017) — default aligned to issue-017's region to avoid splitting regions.
    GOOGLE_CLOUD_PROJECT: str = Field(default="", description="GCP project ID (Vertex AI / Cloud Tasks / GCS).")
    GOOGLE_CLOUD_LOCATION: str = Field(
        default="asia-northeast1", description="GCP region for Vertex AI / Cloud Tasks / GCS."
    )
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash", description="Gemini model ID used by agents.")

    # Async task queue (issue 016). Defaults run a fully in-memory pipeline (no GCP needed).
    USE_MOCK_QUEUE: bool = Field(default=True, description="Use the in-memory TaskDispatcher instead of Cloud Tasks.")
    USE_MOCK_WORKER: bool = Field(
        default=True, description="Run an in-process mock-worker standing in for the service container."
    )
    USE_MOCK_BLOB: bool = Field(default=True, description="Use the in-memory BlobClient instead of GCS.")
    USE_LOCAL_SERVICE: bool = Field(
        default=False,
        description=(
            "Local dev: dispatch tasks over HTTP to a running `service` container "
            "(docker compose) instead of the in-process mock-worker or Cloud Tasks. "
            "Lets service-only pipelines (e.g. stack_analysis) run end-to-end locally."
        ),
    )
    SERVICE_TASKS_URL: str = Field(
        default="http://localhost:8001", description="Cloud Tasks HTTP target — the service container base URL."
    )
    SERVICE_OIDC_AUDIENCE: str = Field(
        default="",
        description=(
            "OIDC token audience for Cloud Tasks → service. Decoupled from SERVICE_TASKS_URL "
            "because the service can't self-reference its own run.app URL in Terraform; a stable "
            "value is wired via the service's custom_audiences. Empty = fall back to SERVICE_TASKS_URL."
        ),
    )
    TASKS_INVOKER_SA: str = Field(
        default="", description="Service account email for the Cloud Tasks → service OIDC token."
    )
    TASKS_QUEUE: str = Field(default="job-requests", description="Cloud Tasks request queue name (issue 017).")
    JOB_PAYLOAD_BUCKET: str = Field(default="", description="GCS bucket for spilled large job payloads (issue 017).")

    # GitHub App (リポジトリアクセス用)
    GITHUB_APP_ID: str = Field(default="", description="GitHub App の数値 ID")
    GITHUB_APP_PRIVATE_KEY: SecretStr = Field(default=SecretStr(""), description="GitHub App の RSA 秘密鍵(PEM 形式)")
    GITHUB_APP_SLUG: str = Field(default="", description="GitHub App のスラッグ(URL に使われる名前)")

    # GitHub OAuth(ユーザー認証用)
    GITHUB_CLIENT_ID: str = Field(default="", description="GitHub OAuth App の Client ID")
    GITHUB_CLIENT_SECRET: SecretStr = Field(default=SecretStr(""), description="GitHub OAuth App の Client Secret")

    # Frontend
    FRONTEND_ORIGIN: str = Field(
        default="http://localhost:5173", description="フロントエンドのオリジン(OAuth コールバック先)"
    )

    # App
    ENVIRONMENT: Literal["dev", "stg", "prod"] = Field(
        default="dev", description="Deployment environment; controls prod-only validations and docs exposure."
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def use_local_service(self) -> bool:
        """Whether to dispatch over HTTP to a running `service` container (local dev)."""
        return self.USE_LOCAL_SERVICE

    def use_mock_queue(self) -> bool:
        """Whether to dispatch via the in-memory mock instead of Cloud Tasks."""
        return self.USE_MOCK_QUEUE and not self.USE_LOCAL_SERVICE

    def use_mock_worker(self) -> bool:
        """Whether to run the in-process mock-worker (stands in for the service container).

        Disabled in local-service mode — the real `service` container processes tasks, so the
        in-process worker (which can only run `shared` pipelines) must not also drain the queue.
        """
        return self.USE_MOCK_WORKER and not self.USE_LOCAL_SERVICE

    def use_mock_blob(self) -> bool:
        """Whether to spill payloads to the in-memory mock blob instead of GCS."""
        return self.USE_MOCK_BLOB

    @model_validator(mode="after")
    def _validate_production_settings(self) -> Self:
        """Enforce security-critical settings in non-dev environments.

        Raises:
            ValueError: If `SECRET_KEY` is still the default placeholder or `COOKIE_SECURE`
                is `False` when `ENVIRONMENT` is not `"dev"`.
        """
        if self.ENVIRONMENT != "dev":
            if self.SECRET_KEY.get_secret_value() == "change-me-in-production":
                raise ValueError("SECRET_KEY must be set to a secure value in non-dev environments")
            if not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SECURE must be true in non-dev environments")
        return self


settings = Settings()
