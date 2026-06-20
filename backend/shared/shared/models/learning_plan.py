"""Shared learning-plan ORM (issue 035): ``LearningPlan`` / ``LearningStep`` / ``LearningResource``.

``learningPlanSchema``（``frontend/src/lib/api/schemas.ts``）に対応。生成パイプラインが資源とステップを埋める。
チーム資産（``origin="team"``）を外部資源より上段に並べるのは配信/生成側の責務。``project_id`` は索引のみ
（FK 無し、Job.project_id 流儀）。``plan_id``/``resource_id`` は shared 内で解決でき FK を張る。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class LearningResource(SQLModel, table=True):
    """A learning resource (team asset or external) referenced by a step."""

    __tablename__ = "learning_resources"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(index=True, nullable=False)
    origin: str = Field(nullable=False)  # team / external
    kind: str = Field(nullable=False)  # adr / video / pr_comment / wiki / docs / book / article / code
    title: str = Field(nullable=False)
    source_ref: str | None = Field(default=None)
    url: str | None = Field(default=None)
    estimated_minutes: int | None = Field(default=None)
    priority: str = Field(nullable=False)  # required / recommended / supplementary / hands_on
    dormant_days: int | None = Field(default=None)
    origin_meta: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class LearningPlan(SQLModel, table=True):
    """A learning plan header (gap concepts + total minutes)."""

    __tablename__ = "learning_plans"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(index=True, nullable=False)
    gap_concepts: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))  # list[str]
    estimated_total_minutes: int = Field(default=0, nullable=False)
    quiz_session_id: uuid.UUID | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


class LearningStep(SQLModel, table=True):
    """An ordered step in a plan, pointing at one resource."""

    __tablename__ = "learning_steps"
    __table_args__ = (UniqueConstraint("plan_id", "order", name="uq_learning_steps_plan_order"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    plan_id: uuid.UUID = Field(foreign_key="learning_plans.id", index=True, nullable=False)
    order: int = Field(nullable=False)
    completed: bool = Field(default=False, nullable=False)
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    resource_id: uuid.UUID = Field(foreign_key="learning_resources.id", nullable=False)
