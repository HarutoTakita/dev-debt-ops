"""add app_metadata key/value table

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``app_metadata`` — a small key/value store for runtime markers (e.g. demo_seed_version)."""
    op.create_table(
        "app_metadata",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_metadata")),
    )


def downgrade() -> None:
    op.drop_table("app_metadata")
