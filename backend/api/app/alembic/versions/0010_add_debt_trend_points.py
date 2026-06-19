"""add debt_trend_points table (issue 031)

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create debt_trend_points (weekly trend snapshots, issue 031).

    読み取り配信のみが本 issue の責務。書き込み（週次スナップショット生成）は 037。
    project_id は索引のみ（FK 無し）。(project_id, week) で一意。
    """
    op.create_table(
        "debt_trend_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("week", sa.String(), nullable=False),
        sa.Column("code_debt_score", sa.Float(), nullable=False),
        sa.Column("knowledge_coverage", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_debt_trend_points")),
        sa.UniqueConstraint("project_id", "week", name="uq_debt_trend_points_project_week"),
    )
    op.create_index(op.f("ix_debt_trend_points_project_id"), "debt_trend_points", ["project_id"], unique=False)


def downgrade() -> None:
    """Drop debt_trend_points."""
    op.drop_index(op.f("ix_debt_trend_points_project_id"), table_name="debt_trend_points")
    op.drop_table("debt_trend_points")
