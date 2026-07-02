from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, sa_created_at, sa_deleted_at, sa_updated_at

if TYPE_CHECKING:
    from app.models.oauth_account import OAuthAccount


class User(SQLAlchemyBaseUserTableUUID, Base):
    """Application user, extending fastapi-users' base table with profile fields.

    Inherits `id`, `email`, `hashed_password`, `is_active`, `is_superuser`, and
    `is_verified` from `SQLAlchemyBaseUserTableUUID`. Locally-added columns are
    `display_name`, `last_active_at`, `created_at`, `updated_at`, `deleted_at`,
    and `token_epoch` (unix seconds; access JWTs with `iat` below this value
    are rejected, enabling immediate logout invalidation).
    """

    __tablename__ = "users"

    display_name: Mapped[str | None] = mapped_column(String)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = sa_created_at()
    updated_at: Mapped[datetime] = sa_updated_at()
    deleted_at: Mapped[datetime | None] = sa_deleted_at()
    token_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    # True for the shared guest-demo account (issue 069): read-only, no GitHub OAuth.
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Remaining repository-analysis credits (issue 298). Each analysis run consumes one; starts at 0
    # and is topped up by an admin. Only enforced when ``ANALYSIS_CREDITS_ENABLED`` (superusers bypass).
    analysis_credits: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    oauth_accounts: Mapped[list[OAuthAccount]] = relationship("OAuthAccount", back_populates="user", lazy="joined")
