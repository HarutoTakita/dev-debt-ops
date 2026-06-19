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
    JWT_LIFETIME_SECONDS: int = Field(default=300, description="Access-token lifetime in seconds (5 min).")
    REFRESH_TOKEN_LIFETIME_SECONDS: int = Field(default=604_800, description="Refresh-token lifetime in seconds (7 d).")

    # AI (Google Gemini via Vertex AI)
    GOOGLE_CLOUD_PROJECT: str = Field(default="", description="Google Cloud project ID for Vertex AI.")
    GOOGLE_CLOUD_LOCATION: str = Field(default="us-central1", description="Vertex AI region (e.g. us-central1).")
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash", description="Gemini model ID used by agents.")

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
