"""add learning_resources.section + summary (issue 068)

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """学習プランを「コード具体（code）」「技術スタック一般（stack）」の2セクションに分けるための列（issue 068）。

    既存行は section=code / summary='' で後方互換。server_default で backfill する。
    """
    op.add_column("learning_resources", sa.Column("section", sa.String(), nullable=False, server_default="code"))
    op.add_column("learning_resources", sa.Column("summary", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("learning_resources", "summary")
    op.drop_column("learning_resources", "section")
