"""add learning_plans.feature_id (issue 063)

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Scope a learning plan to a feature unit (index-only, no FK; issue 063)."""
    op.add_column("learning_plans", sa.Column("feature_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_learning_plans_feature_id"), "learning_plans", ["feature_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_learning_plans_feature_id"), table_name="learning_plans")
    op.drop_column("learning_plans", "feature_id")
