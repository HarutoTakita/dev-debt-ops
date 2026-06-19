"""Shared ``Job`` ORM model — single source of truth for the async job lifecycle.

Shared by ``api`` (enqueue + read) and ``service`` (result write). ``api`` owns the
Alembic migrations and the DB engine/session; ``service`` writes results via its own
thin session (``service/db.py``). Fields here are a baseline — issue 016 / 018 finalize
the schema (and add the migration that creates this table).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, String, func
from sqlmodel import Field, SQLModel

from shared.enums import JobStatus, JobType


class Job(SQLModel, table=True):
    """An asynchronous unit of work dispatched from api to service via the queue.

    api creates the row as ``QUEUED`` and reads it for ``GET /jobs/{id}``; service
    updates it to ``COMPLETED`` / ``FAILED`` with ``result_data`` after processing
    (issue 016 / 018).
    """

    __tablename__ = "jobs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # Enums are stored as String (project convention, cf. OrgRole) — no native PG enum types.
    job_type: JobType = Field(sa_type=String, index=True)
    status: JobStatus = Field(default=JobStatus.QUEUED, sa_type=String, index=True)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    result_data: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    error: str | None = Field(default=None)
    created_by: uuid.UUID | None = Field(default=None, index=True)
    project_id: uuid.UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
