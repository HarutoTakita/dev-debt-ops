"""Shared ``FeatureFlag`` ORM — a user's per-project flag ("pin") on a feature unit.

Lets a developer flag feature units in the learn→confirm hub so flagged ones sort to the top.
Persisted by ``(developer_id, project_id, feature_key)`` — features are re-created every analysis
run, so the stable key is ``feature_key`` (not the per-run ``features.id``). ``project_id`` is an
index only (FK-less, ``Job.project_id`` convention).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class FeatureFlag(SQLModel, table=True):
    """One developer's flag on one feature (by stable key) within a project."""

    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("developer_id", "project_id", "feature_key", name="uq_feature_flags_dev_project_key"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    developer_id: uuid.UUID = Field(index=True, nullable=False)  # = users.id
    project_id: uuid.UUID = Field(index=True, nullable=False)
    feature_key: str = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
