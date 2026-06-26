"""add users.is_demo

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``is_demo`` flag to users (guest demo, issue 069). Existing rows default false."""
    op.add_column("users", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("users", "is_demo")
