"""add stale flag to quiz_sessions and learning_plans

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-12

Incremental re-analysis (Phase 2a): when a feature's file set changes on re-analysis, its quizzes /
learning plans are flagged ``stale`` so the UI prompts a re-take ("要再受験", the repayment-loop signal).
Expand-only / N-1 compatible: NOT NULL with a ``false`` server default so blue (old) revisions keep
inserting rows without the column (they get ``false``), and existing rows backfill to ``false``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``stale`` (NOT NULL default false) to quiz_sessions + learning_plans."""
    for table in ("quiz_sessions", "learning_plans"):
        op.add_column(table, sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("learning_plans", "stale")
    op.drop_column("quiz_sessions", "stale")
