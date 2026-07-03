"""add feature_flags

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``feature_flags`` — a developer's per-project flag on a feature unit (by stable key)."""
    op.create_table(
        "feature_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("developer_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("feature_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_feature_flags"),
        sa.UniqueConstraint("developer_id", "project_id", "feature_key", name="uq_feature_flags_dev_project_key"),
    )
    op.create_index("ix_feature_flags_developer_id", "feature_flags", ["developer_id"])
    op.create_index("ix_feature_flags_project_id", "feature_flags", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_feature_flags_project_id", table_name="feature_flags")
    op.drop_index("ix_feature_flags_developer_id", table_name="feature_flags")
    op.drop_table("feature_flags")
