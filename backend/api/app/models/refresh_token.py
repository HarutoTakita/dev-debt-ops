import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, sa_deleted_at


class RefreshToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    """Opaque server-side refresh token with rotation + reuse-detection metadata.

    Inherits `token` (PK, opaque string) and `created_at` from
    `SQLAlchemyBaseAccessTokenTableUUID`. Overrides the parent class's `user_id`
    FK to point at `users.id` (the parent defaults to a `user` table). Adds
    rotation metadata: `family_id` groups the rotation chain; `revoked_at` and
    `replaced_by_token` drive reuse-detection.
    """

    __tablename__ = "refresh_tokens"

    # Override parent's user.id FK — our users table is plural.
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="cascade"), nullable=False)

    family_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = sa_deleted_at()
    replaced_by_token: Mapped[str | None] = mapped_column(String, nullable=True)
