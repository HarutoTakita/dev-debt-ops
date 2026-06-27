"""add learning_resources.tech (issue 068)

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """技術スタック資源に「学べるテックスタック」タグ列を追加する（issue 068）。

    既存行は tech='' で後方互換。server_default で backfill する。
    """
    op.add_column("learning_resources", sa.Column("tech", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("learning_resources", "tech")
