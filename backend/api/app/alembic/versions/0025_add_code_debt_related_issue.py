"""add code_debts.related_issue

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``related_issue`` column to code_debts (人に頼む経路の GitHub issue URL, issue 210). Nullable."""
    op.add_column("code_debts", sa.Column("related_issue", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("code_debts", "related_issue")
