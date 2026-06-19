"""add file_kc and dependencies tables (issue 029)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create file_kc (KC per file / per dev) and dependencies (wormholes), issue 029.

    file_kc は dev 行（dev_id 非 NULL）と集計行（dev_id IS NULL）を 1 テーブルに持つ。
    集計行を 1 本に保つため (run_id, file_path) の部分ユニーク索引を WHERE dev_id IS NULL で張る。
    """
    op.create_table(
        "file_kc",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("module", sa.String(), nullable=False),
        sa.Column("dev_id", sa.Uuid(), nullable=True),
        sa.Column("github_handle", sa.String(), nullable=True),
        sa.Column("kc", sa.Float(), nullable=False),
        sa.Column("mastery", sa.String(), nullable=False),
        sa.Column("certified_via", sa.String(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], name=op.f("fk_file_kc_run_id_analysis_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_kc")),
    )
    op.create_index(op.f("ix_file_kc_run_id"), "file_kc", ["run_id"], unique=False)
    op.create_index(op.f("ix_file_kc_file_path"), "file_kc", ["file_path"], unique=False)
    op.create_index(op.f("ix_file_kc_dev_id"), "file_kc", ["dev_id"], unique=False)
    # 行種別ごとに互いに素な 3 つの部分ユニーク索引（NULL の区別を避け、未突合 author 行と集計行の衝突も防ぐ）。
    op.create_index(
        "uq_file_kc_dev",
        "file_kc",
        ["run_id", "file_path", "dev_id"],
        unique=True,
        postgresql_where=sa.text("dev_id IS NOT NULL"),
    )
    op.create_index(
        "uq_file_kc_handle",
        "file_kc",
        ["run_id", "file_path", "github_handle"],
        unique=True,
        postgresql_where=sa.text("dev_id IS NULL AND github_handle IS NOT NULL"),
    )
    op.create_index(
        "uq_file_kc_agg",
        "file_kc",
        ["run_id", "file_path"],
        unique=True,
        postgresql_where=sa.text("dev_id IS NULL AND github_handle IS NULL"),
    )

    op.create_table(
        "dependencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("from_path", sa.String(), nullable=False),
        sa.Column("to_path", sa.String(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], name=op.f("fk_dependencies_run_id_analysis_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dependencies")),
        sa.UniqueConstraint("run_id", "from_path", "to_path", name="uq_dependencies_run_from_to"),
    )
    op.create_index(op.f("ix_dependencies_run_id"), "dependencies", ["run_id"], unique=False)


def downgrade() -> None:
    """Drop dependencies then file_kc."""
    op.drop_index(op.f("ix_dependencies_run_id"), table_name="dependencies")
    op.drop_table("dependencies")
    op.drop_index("uq_file_kc_agg", table_name="file_kc")
    op.drop_index("uq_file_kc_handle", table_name="file_kc")
    op.drop_index("uq_file_kc_dev", table_name="file_kc")
    op.drop_index(op.f("ix_file_kc_dev_id"), table_name="file_kc")
    op.drop_index(op.f("ix_file_kc_file_path"), table_name="file_kc")
    op.drop_index(op.f("ix_file_kc_run_id"), table_name="file_kc")
    op.drop_table("file_kc")
