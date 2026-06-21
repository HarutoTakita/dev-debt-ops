"""Shared ``FeatureFile`` ORM model — feature↔file mapping for one run (issue 052).

The many-to-many mapping between a clustered ``Feature`` and the source files it owns (one file
may belong to several features). ``file_path`` is the File-identity anchor (joins to ``repo_file``
/ ``file_kc``), which is what issue 055 joins to roll KC/debts up to the feature granularity.
``api`` owns the Alembic migration; ``service`` only DMLs this from the clustering pipeline.
"""

import uuid

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class FeatureFile(SQLModel, table=True):
    """One (feature, file) membership within an analysis run."""

    __tablename__ = "feature_files"
    __table_args__ = (UniqueConstraint("run_id", "feature_id", "file_path", name="uq_feature_files_run_feature_path"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="analysis_runs.id", index=True, nullable=False)
    feature_id: uuid.UUID = Field(foreign_key="features.id", index=True, nullable=False)
    file_path: str = Field(index=True, nullable=False, description="File-identity anchor (joins repo_file / file_kc).")
    confidence: float = Field(default=1.0, nullable=False, description="Gemini attribution confidence (0..1).")
