"""add learning_plans.developer_id (issue 040)

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the (index-only, no FK) owner column for personal learning plans."""
    op.add_column("learning_plans", sa.Column("developer_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_learning_plans_developer_id"), "learning_plans", ["developer_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_learning_plans_developer_id"), table_name="learning_plans")
    op.drop_column("learning_plans", "developer_id")
