"""add jobs.progress

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``progress`` JSON column to jobs (live multi-step progress, issue 069). Nullable."""
    op.add_column("jobs", sa.Column("progress", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "progress")
