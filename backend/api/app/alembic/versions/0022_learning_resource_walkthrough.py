"""add learning_resources.walkthrough

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """コード理解の行ごと解説（オンデマンド生成・保存）を格納する JSON 列を追加する。

    既存行は空配列で後方互換。server_default で backfill する。
    """
    op.add_column(
        "learning_resources",
        sa.Column("walkthrough", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )


def downgrade() -> None:
    op.drop_column("learning_resources", "walkthrough")
