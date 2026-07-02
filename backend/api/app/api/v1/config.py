"""Public runtime config endpoint — feature flags the SPA needs before authentication."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(tags=["Config"])


class PublicConfig(BaseModel):
    """Unauthenticated runtime config consumed by the SPA at boot."""

    demo_mode_enabled: bool
    analysis_credits_enabled: bool


@router.get("/config", response_model=PublicConfig, summary="Public runtime config / feature flags")
async def get_public_config() -> PublicConfig:
    """Return feature flags the frontend needs before login (e.g. whether to show the demo button)."""
    return PublicConfig(
        demo_mode_enabled=settings.DEMO_MODE_ENABLED,
        analysis_credits_enabled=settings.ANALYSIS_CREDITS_ENABLED,
    )
