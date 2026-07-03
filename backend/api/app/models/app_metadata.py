from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, sa_updated_at


class AppMetadata(Base):
    """Small key/value store for app-level runtime markers (not user-facing).

    Currently holds ``demo_seed_version`` — the ``DEMO_SEED_VERSION`` already applied to the demo
    dataset — so the startup guard (``seed_demo.refresh_demo_if_stale``) reseeds only when the demo
    content version changes, instead of on every boot.
    """

    __tablename__ = "app_metadata"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = sa_updated_at()
