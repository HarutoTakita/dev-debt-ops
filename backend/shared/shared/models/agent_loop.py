"""Shared Twin-Agent loop ORM (issue 036): pipeline / activity / narrative step / evidence.

The loop pipeline binds the detection/repayment domains (028-034) into a 5-stage state machine
(``stages`` JSON) plus a first-person narrative with archaeology evidence. Matches the Zod contract
(``agentPipelineSchema`` / ``agentActivitySchema`` / ``narrativeStepSchema`` / ``narrativeEvidenceSchema``).
``project_id`` is indexed (no FK); agent profiles are static api constants (no table).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, func
from sqlmodel import Field, SQLModel


class AgentPipeline(SQLModel, table=True):
    """The 5-stage pipeline state machine (stages folded into JSON)."""

    __tablename__ = "agent_pipelines"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(index=True, nullable=False)
    kind: str = Field(nullable=False)  # code_debt / knowledge_debt
    status: str = Field(default="pending", nullable=False)
    stages: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))  # pipelineStageSchema[]
    job_id: uuid.UUID | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class AgentActivity(SQLModel, table=True):
    """A narrative activity (headline + steps), referencing one pipeline."""

    __tablename__ = "agent_activities"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(index=True, nullable=False)
    kind: str = Field(nullable=False)
    headline: str = Field(nullable=False)
    pipeline_id: uuid.UUID = Field(foreign_key="agent_pipelines.id", index=True, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class NarrativeStep(SQLModel, table=True):
    """One first-person thinking step of an activity."""

    __tablename__ = "narrative_steps"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    activity_id: uuid.UUID = Field(foreign_key="agent_activities.id", index=True, nullable=False)
    order: int = Field(nullable=False)
    status: str = Field(nullable=False)
    message: str = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class NarrativeEvidence(SQLModel, table=True):
    """A piece of archaeology evidence attached to a narrative step."""

    __tablename__ = "narrative_evidence"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    step_id: uuid.UUID = Field(foreign_key="narrative_steps.id", index=True, nullable=False)
    type: str = Field(nullable=False)  # first_commit / ai_generated / adr_reference / pr_review
    label: str = Field(nullable=False)
    detail: str | None = Field(default=None)
    href: str | None = Field(default=None)
