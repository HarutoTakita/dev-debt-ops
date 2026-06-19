"""Shared ``QuizAnswer`` ORM — one saved answer (issue 034).

``quizAnswerSchema``（``frontend/src/lib/api/schemas.ts``）に対応。途中保存は ``(session_id, question_id)`` を
キーに upsert する。
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class QuizAnswer(SQLModel, table=True):
    """One answer to one quiz question (upsert on save)."""

    __tablename__ = "quiz_answers"
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="uq_quiz_answers_session_question"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="quiz_sessions.id", index=True, nullable=False)
    question_id: str = Field(nullable=False)
    value: str = Field(default="", nullable=False)  # MC は choice id、free_text は本文
    saved_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
