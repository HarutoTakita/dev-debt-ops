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

    # AI (Google Gemini)
    GOOGLE_API_KEY: SecretStr = Field(
        default=SecretStr(""), description="API key for Google Generative AI (Gemini)."
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
