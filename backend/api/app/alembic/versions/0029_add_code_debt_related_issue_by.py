"""add code_debts.related_issue_by

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``related_issue_by`` (= users.id) to code_debts for the admin dashboard's per-member Issue count.

    Nullable + index-only (no FK, mirrors project_id convention). Existing rows stay NULL.
    """
    op.add_column("code_debts", sa.Column("related_issue_by", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_code_debts_related_issue_by"), "code_debts", ["related_issue_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_code_debts_related_issue_by"), table_name="code_debts")
    op.drop_column("code_debts", "related_issue_by")
