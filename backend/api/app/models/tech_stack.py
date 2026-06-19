"""TechStack model: stores Gemini-analysed technology stack for a repository."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import uuid7_pk


class TechStack(SQLModel, table=True):
    """Cached result of a Gemini tech-stack analysis for one repository.

    One row per (owner, repo) pair; re-analysis overwrites the row in place.
    """

    __tablename__ = "tech_stacks"
    __table_args__ = (UniqueConstraint("owner", "repo", name="uq_tech_stacks_owner_repo"),)

    id: uuid.UUID = uuid7_pk()
    owner: str = Field(nullable=False, index=True, description="GitHub repository owner (user or org).")
    repo: str = Field(nullable=False, index=True, description="GitHub repository name.")
    analyzed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp of the most recent analysis.",
    )
    languages: list = Field(
        default=[],
        sa_column=Column(JSON, nullable=False),
        description='[{"name": "TypeScript", "confidence": "high"}, ...]',
    )
    categories: dict = Field(
        default={},
        sa_column=Column(JSON, nullable=False),
        description='{"frameworks": [...], "databases": [...], ...}',
    )
