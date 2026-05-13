"""OAuth account linked to a user (e.g. GitHub)."""

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseOAuthAccountTableUUID
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    """OAuth account row, one per provider per user."""

    __tablename__ = "oauth_accounts"

    user_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="cascade"), nullable=False)

    user: Mapped["User"] = relationship(back_populates="oauth_accounts")


from app.models.user import User  # noqa: E402
