"""Shared ``Feature`` ORM model — AI-clustered product feature for one analysis run (issue 052).

A *feature* is a semantic grouping of files (e.g. 認証 / 課金 / 解析パイプライン) above the
directory level, derived by Gemini clustering. It is the coarsest measurement granularity
(``Granularity.FEATURE``) and is independent of folder structure. Results are snapshotted per
``run_id`` so the non-deterministic clustering is a fixed value within a run. ``api`` owns the
Alembic migration; ``service`` only DMLs this table from the clustering pipeline.

``id`` uses a plain ``uuid4`` default to keep ``shared`` dependency-light (matches ``TechStack``).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class Feature(SQLModel, table=True):
    """One AI-clustered product feature within an analysis run."""

    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("run_id", "key", name="uq_features_run_key"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(index=True, nullable=False)
    run_id: uuid.UUID = Field(foreign_key="analysis_runs.id", index=True, nullable=False)
    key: str = Field(nullable=False, description="Stable slug (e.g. 'auth', 'billing') for cross-run tracking.")
    name: str = Field(nullable=False, description="Display name (e.g. '認証').")
    description: str = Field(default="", nullable=False, description="1-2 line Gemini description of the feature.")
    # Derivation source: 'ai' (this issue) or 'manual' (future manual edits via a settings UI).
    source: str = Field(default="ai", nullable=False)
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
