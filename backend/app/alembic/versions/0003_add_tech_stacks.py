"""add tech_stacks table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tech_stacks table."""
    op.create_table(
        "tech_stacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tech_stacks")),
        sa.UniqueConstraint("owner", "repo", name="uq_tech_stacks_owner_repo"),
    )
    op.create_index(op.f("ix_tech_stacks_owner"), "tech_stacks", ["owner"], unique=False)
    op.create_index(op.f("ix_tech_stacks_repo"), "tech_stacks", ["repo"], unique=False)


def downgrade() -> None:
    """Drop tech_stacks table."""
    op.drop_index(op.f("ix_tech_stacks_repo"), table_name="tech_stacks")
    op.drop_index(op.f("ix_tech_stacks_owner"), table_name="tech_stacks")
    op.drop_table("tech_stacks")
