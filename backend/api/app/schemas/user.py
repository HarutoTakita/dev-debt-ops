import uuid
from datetime import datetime
from typing import Literal

from fastapi_users import schemas
from pydantic import BaseModel, Field


class UserRead(schemas.BaseUser[uuid.UUID]):
    """User as exposed to API clients.

    Inherits `id`, `email`, `is_active`, `is_superuser`, and `is_verified` from
    `BaseUser`. Locally-added fields are `display_name`, `created_at`, and
    `last_active_at`.
    """

    display_name: str | None = Field(default=None, description="Optional user-chosen display name.")
    created_at: datetime | None = Field(
        default=None,
        description="Timestamp when the user account was created; nullable due to pre-migration rows.",
    )
    last_active_at: datetime | None = Field(
        default=None,
        description="Timestamp of the user's last authenticated activity; nullable due to pre-migration rows.",
    )
    is_demo: bool = Field(
        default=False,
        description="True for the shared guest-demo user (read-only, no GitHub); drives demo UI gating.",
    )
    analysis_credits: int = Field(
        default=0,
        description="Remaining repository-analysis credits (issue 298); drives the analysis/PR button gating.",
    )


class UserCreate(schemas.BaseUserCreate):
    """Body for user registration."""

    display_name: str | None = Field(default=None, description="Optional user-chosen display name.")


class UserUpdate(schemas.BaseUserUpdate):
    """Body for user profile updates."""

    display_name: str | None = Field(default=None, description="Optional user-chosen display name.")


class UserRoleUpdate(BaseModel):
    """Request body for promoting or demoting a user's role (admin-only endpoint)."""

    role: Literal["admin", "user"] = Field(description="Target role: 'admin' grants is_superuser; 'user' revokes it.")


class UserCreditsGrant(BaseModel):
    """Request body for granting repository-analysis credits to a user (admin-only, issue 298)."""

    amount: int = Field(ge=1, le=1000, description="Number of analysis credits to add to the user's balance.")
