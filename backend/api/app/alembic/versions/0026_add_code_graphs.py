"""add code_graphs

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``code_graphs`` — one CodeGraphContext snapshot per project (issue 235)."""
    op.create_table(
        "code_graphs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("graph", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_code_graphs_project"),
    )
    op.create_index(op.f("ix_code_graphs_project_id"), "code_graphs", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_code_graphs_project_id"), table_name="code_graphs")
    op.drop_table("code_graphs")
