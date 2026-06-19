"""Shared ``TechStack`` ORM model — cached Gemini tech-stack analysis for one repo.

Promoted from api's ``app.models.tech_stack`` to ``shared`` (issue 018) because ``service``
now writes this row directly after running the async analysis pipeline, while ``api`` still
reads it for ``GET .../stack``. ``api`` owns the Alembic migration that creates the table
(``0003_add_tech_stacks``); the schema here is unchanged (same columns + unique constraint).

The id uses a plain ``uuid4`` default to keep ``shared`` dependency-light (``pydantic`` +
``sqlmodel`` only — no ``uuid-utils``), matching ``shared.models.Job``.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class TechStack(SQLModel, table=True):
    """Cached result of a Gemini tech-stack analysis for one repository.

    One row per (owner, repo) pair; re-analysis overwrites the row in place.
    """

    __tablename__ = "tech_stacks"
    __table_args__ = (UniqueConstraint("owner", "repo", name="uq_tech_stacks_owner_repo"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
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
