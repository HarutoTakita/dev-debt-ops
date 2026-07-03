"""quiz per-question correctness + question flags + retest lineage

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add per-question correctness (#4), question flags (#6), and retest lineage (#6)."""
    # #4/#6: per-question correctness, set at grade time (NULL until graded).
    op.add_column("quiz_answers", sa.Column("is_correct", sa.Boolean(), nullable=True))

    # #6: retest lineage — a filtered retest session points to its origin (chain root) + records its mode.
    op.add_column("quiz_sessions", sa.Column("origin_session_id", sa.Uuid(), nullable=True))
    op.add_column("quiz_sessions", sa.Column("retest_mode", sa.String(), nullable=True))
    op.create_index("ix_quiz_sessions_origin_session_id", "quiz_sessions", ["origin_session_id"])

    # #6: a developer's flag on one question within a session.
    op.create_table(
        "quiz_question_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("developer_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["quiz_sessions.id"], name="fk_quiz_question_flags_session"),
        sa.PrimaryKeyConstraint("id", name="pk_quiz_question_flags"),
        sa.UniqueConstraint("developer_id", "session_id", "question_id", name="uq_quiz_question_flags_dev_session_q"),
    )
    op.create_index("ix_quiz_question_flags_developer_id", "quiz_question_flags", ["developer_id"])
    op.create_index("ix_quiz_question_flags_session_id", "quiz_question_flags", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_quiz_question_flags_session_id", table_name="quiz_question_flags")
    op.drop_index("ix_quiz_question_flags_developer_id", table_name="quiz_question_flags")
    op.drop_table("quiz_question_flags")
    op.drop_index("ix_quiz_sessions_origin_session_id", table_name="quiz_sessions")
    op.drop_column("quiz_sessions", "retest_mode")
    op.drop_column("quiz_sessions", "origin_session_id")
    op.drop_column("quiz_answers", "is_correct")
