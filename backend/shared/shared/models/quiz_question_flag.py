"""Shared ``QuizQuestionFlag`` ORM — a developer's flag on one quiz question (#6).

Per (developer, session, question). Flagged questions can be re-tested in isolation
(``retest`` with ``mode="flagged"``). Upsert-free: set = insert-if-absent, clear = delete.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class QuizQuestionFlag(SQLModel, table=True):
    """One developer's flag on one question within a quiz session."""

    __tablename__ = "quiz_question_flags"
    __table_args__ = (
        UniqueConstraint("developer_id", "session_id", "question_id", name="uq_quiz_question_flags_dev_session_q"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    developer_id: uuid.UUID = Field(index=True, nullable=False)  # = users.id
    session_id: uuid.UUID = Field(foreign_key="quiz_sessions.id", index=True, nullable=False)
    question_id: str = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
