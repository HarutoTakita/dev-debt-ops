"""add feature_key to quiz_sessions and learning_plans

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-12

Incremental re-analysis (Phase 1): quizzes/learning plans must survive re-analysis. ``features.id`` is
regenerated every analysis run, so the stable link is ``features.key`` (same rationale as
``feature_flags``). Add a nullable ``feature_key`` and backfill from the still-resolvable
``feature_id`` -> ``features.key``. Expand-only / N-1 compatible: the column is nullable so blue (old)
revisions keep writing rows without it; green (new) code falls back to ``feature_id`` when it is NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable ``feature_key`` to quiz_sessions + learning_plans and backfill from features.key."""
    op.add_column("quiz_sessions", sa.Column("feature_key", sa.String(), nullable=True))
    op.add_column("learning_plans", sa.Column("feature_key", sa.String(), nullable=True))
    op.create_index("ix_quiz_sessions_feature_key", "quiz_sessions", ["feature_key"])
    op.create_index("ix_learning_plans_feature_key", "learning_plans", ["feature_key"])

    # Backfill from the per-run feature id that is still resolvable (pruned old-run features stay NULL
    # and fall back to feature_id at query time).
    op.execute(
        """
        UPDATE quiz_sessions AS q
        SET feature_key = f.key
        FROM features AS f
        WHERE q.feature_id = f.id AND q.feature_key IS NULL
        """
    )
    op.execute(
        """
        UPDATE learning_plans AS p
        SET feature_key = f.key
        FROM features AS f
        WHERE p.feature_id = f.id AND p.feature_key IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_learning_plans_feature_key", table_name="learning_plans")
    op.drop_index("ix_quiz_sessions_feature_key", table_name="quiz_sessions")
    op.drop_column("learning_plans", "feature_key")
    op.drop_column("quiz_sessions", "feature_key")
