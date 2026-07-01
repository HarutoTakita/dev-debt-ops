"""add base_analysis_snapshots

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``base_analysis_snapshots`` — one Base Analysis Agent output per project (issue 266)."""
    op.create_table(
        "base_analysis_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_base_analysis_snapshots_project"),
    )
    op.create_index(
        op.f("ix_base_analysis_snapshots_project_id"), "base_analysis_snapshots", ["project_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_base_analysis_snapshots_project_id"), table_name="base_analysis_snapshots")
    op.drop_table("base_analysis_snapshots")
