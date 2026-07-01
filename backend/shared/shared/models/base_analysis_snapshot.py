"""Shared ``BaseAnalysisSnapshot`` ORM — the latest Base Analysis Agent output per project (issue 266).

Agent-first re-architecture: ``service`` writes the qualitative ``BaseAnalysis`` (features / findings /
risk narrative) the Base Analysis Agent produces at the start of an agentic analysis, so downstream
blocks (and re-runs) can consume it without re-invoking the LLM. One row per project, overwritten in
place on re-analysis — same shape/rationale as ``CodeGraph`` (issue 235). ``api`` owns the Alembic
migration (``0027_add_base_analysis_snapshots``). Dependency-light (``uuid4`` default) like the other
shared models; ``payload`` holds ``BaseAnalysis.model_dump()``.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class BaseAnalysisSnapshot(SQLModel, table=True):
    """Latest Base Analysis Agent output for one project (one row per project, upserted)."""

    __tablename__ = "base_analysis_snapshots"
    __table_args__ = (UniqueConstraint("project_id", name="uq_base_analysis_snapshots_project"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(nullable=False, index=True, description="Owning project id.")
    computed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp of the most recent base-analysis snapshot.",
    )
    payload: dict = Field(
        default={},
        sa_column=Column(JSON, nullable=False),
        description="BaseAnalysis.model_dump(): {features, code_findings, knowledge_findings, stack_terms, summary}.",
    )
