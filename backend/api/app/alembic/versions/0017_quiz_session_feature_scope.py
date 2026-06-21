"""add quiz_sessions.granularity / feature_id / is_baseline (issue 054)

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add feature-scope columns to quiz_sessions (backward compatible defaults)."""
    op.add_column("quiz_sessions", sa.Column("granularity", sa.String(), nullable=False, server_default="file"))
    op.add_column("quiz_sessions", sa.Column("feature_id", sa.Uuid(), nullable=True))
    op.add_column("quiz_sessions", sa.Column("is_baseline", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("quiz_sessions", "is_baseline")
    op.drop_column("quiz_sessions", "feature_id")
    op.drop_column("quiz_sessions", "granularity")
