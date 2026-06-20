"""set analysis_runs.branch server_default 'main' (issue 042)

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a server_default so non-ORM inserts that omit ``branch`` don't NOT-NULL-violate."""
    op.alter_column("analysis_runs", "branch", server_default=sa.text("'main'"))


def downgrade() -> None:
    op.alter_column("analysis_runs", "branch", server_default=None)
