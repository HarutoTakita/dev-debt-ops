from datetime import datetime

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, sa_created_at, sa_deleted_at, sa_updated_at


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
