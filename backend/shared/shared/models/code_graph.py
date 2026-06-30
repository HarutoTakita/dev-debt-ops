"""Shared ``CodeGraph`` ORM model — persisted CodeGraphContext snapshot for one project (issue 235).

``service`` writes a compact node-link snapshot (function call graph) after building the CGC graph
during agentic analysis; ``api`` reads it for ``GET .../code-graph`` (a future UI renders it). One row
per project, overwritten in place on re-analysis. ``api`` owns the Alembic migration
(``0026_add_code_graphs``). Dependency-light (``uuid4`` default) like the other shared models.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class CodeGraph(SQLModel, table=True):
    """Latest CodeGraphContext snapshot for one project (one row per project, upserted)."""

    __tablename__ = "code_graphs"
    __table_args__ = (UniqueConstraint("project_id", name="uq_code_graphs_project"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(nullable=False, index=True, description="Owning project id.")
    computed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp of the most recent graph snapshot.",
    )
    graph: dict = Field(
        default={},
        sa_column=Column(JSON, nullable=False),
        description='Node-link snapshot: {"nodes": [{"id"}], "edges": [{"source","target"}]}.',
    )
