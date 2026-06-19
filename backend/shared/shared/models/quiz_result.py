"""Shared ``QuizResult`` ORM — grading outcome for one session (issue 034).

``quizResultSchema``（``frontend/src/lib/api/schemas.ts``）に対応。``kc_before``/``kc_after`` は採点パイプライン内の
**暫定値**（KC 本算出は issue 029）。``learning_plan_id`` は issue 035 が発番、本 issue は紐付け列のみ。
"""

import uuid

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class QuizResult(SQLModel, table=True):
    """The graded result of one quiz session (one row per session)."""

    __tablename__ = "quiz_results"
    __table_args__ = (UniqueConstraint("session_id", name="uq_quiz_results_session"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="quiz_sessions.id", index=True, nullable=False)
    understood: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))  # Concept[]
    gap_concepts: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))  # Concept[]
    kc_before: float = Field(default=0.0, nullable=False)  # 暫定（本算出は 029）
    kc_after: float = Field(default=0.0, nullable=False)  # 暫定
    learning_plan_id: uuid.UUID | None = Field(default=None)  # 035 が発番
