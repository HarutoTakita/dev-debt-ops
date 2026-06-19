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


class UserCreate(schemas.BaseUserCreate):
    """Body for user registration."""

    display_name: str | None = Field(default=None, description="Optional user-chosen display name.")


class UserUpdate(schemas.BaseUserUpdate):
    """Body for user profile updates."""

    display_name: str | None = Field(default=None, description="Optional user-chosen display name.")


class UserRoleUpdate(BaseModel):
    """Request body for promoting or demoting a user's role (admin-only endpoint)."""

    role: Literal["admin", "user"] = Field(description="Target role: 'admin' grants is_superuser; 'user' revokes it.")
