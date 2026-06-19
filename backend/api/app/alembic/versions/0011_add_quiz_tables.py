"""add quiz_sessions / quiz_answers / quiz_results tables (issue 034)

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the quiz tables (issue 034). project_id/developer_id are indexed (no FK)."""
    op.create_table(
        "quiz_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("developer_id", sa.Uuid(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("repo_full_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column("answer_key", sa.JSON(), nullable=False),
        sa.Column("source_kc", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_sessions")),
    )
    op.create_index(op.f("ix_quiz_sessions_project_id"), "quiz_sessions", ["project_id"], unique=False)
    op.create_index(op.f("ix_quiz_sessions_developer_id"), "quiz_sessions", ["developer_id"], unique=False)

    op.create_table(
        "quiz_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["quiz_sessions.id"], name=op.f("fk_quiz_answers_session_id_quiz_sessions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_answers")),
        sa.UniqueConstraint("session_id", "question_id", name="uq_quiz_answers_session_question"),
    )
    op.create_index(op.f("ix_quiz_answers_session_id"), "quiz_answers", ["session_id"], unique=False)

    op.create_table(
        "quiz_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("understood", sa.JSON(), nullable=False),
        sa.Column("gap_concepts", sa.JSON(), nullable=False),
        sa.Column("kc_before", sa.Float(), nullable=False),
        sa.Column("kc_after", sa.Float(), nullable=False),
        sa.Column("learning_plan_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["quiz_sessions.id"], name=op.f("fk_quiz_results_session_id_quiz_sessions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_results")),
        sa.UniqueConstraint("session_id", name="uq_quiz_results_session"),
    )
    op.create_index(op.f("ix_quiz_results_session_id"), "quiz_results", ["session_id"], unique=False)


def downgrade() -> None:
    """Drop quiz_results, quiz_answers, quiz_sessions (FK-reverse order)."""
    op.drop_index(op.f("ix_quiz_results_session_id"), table_name="quiz_results")
    op.drop_table("quiz_results")
    op.drop_index(op.f("ix_quiz_answers_session_id"), table_name="quiz_answers")
    op.drop_table("quiz_answers")
    op.drop_index(op.f("ix_quiz_sessions_developer_id"), table_name="quiz_sessions")
    op.drop_index(op.f("ix_quiz_sessions_project_id"), table_name="quiz_sessions")
    op.drop_table("quiz_sessions")
