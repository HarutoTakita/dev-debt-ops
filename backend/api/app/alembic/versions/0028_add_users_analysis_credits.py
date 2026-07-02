"""add users.analysis_credits

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``analysis_credits`` balance to users (issue 298). Existing rows default to 0."""
    op.add_column("users", sa.Column("analysis_credits", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "analysis_credits")
