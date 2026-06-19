"""add analysis_runs and repo_files tables, enable pgvector

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable pgvector and create the shared analysis foundation tables (issue 026).

    全解析ドメイン（028 以降）が共有する土台: analysis_run（snapshot 軸）/ repo_file（File 同一性）。
    pgvector は将来の埋め込み類似検索の前提配線のみ（本 issue では vector 列は持たない）。
    """
    # 重複検知・概念マッピングの埋め込み類似検索の前提配線（冪等。本 issue では vector 列は作らない）。
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("commit_sha", sa.String(), nullable=False),
        sa.Column("branch", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_analysis_runs_project_id_projects")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_analysis_runs_job_id_jobs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_runs")),
    )
    op.create_index(op.f("ix_analysis_runs_project_id"), "analysis_runs", ["project_id"], unique=False)
    op.create_index(op.f("ix_analysis_runs_commit_sha"), "analysis_runs", ["commit_sha"], unique=False)
    op.create_index(op.f("ix_analysis_runs_kind"), "analysis_runs", ["kind"], unique=False)
    op.create_index(op.f("ix_analysis_runs_job_id"), "analysis_runs", ["job_id"], unique=False)
    op.create_index(op.f("ix_analysis_runs_status"), "analysis_runs", ["status"], unique=False)

    op.create_table(
        "repo_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("loc", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], name=op.f("fk_repo_files_run_id_analysis_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repo_files")),
        sa.UniqueConstraint("run_id", "path", name="uq_repo_files_run_id_path"),
    )
    op.create_index(op.f("ix_repo_files_run_id"), "repo_files", ["run_id"], unique=False)


def downgrade() -> None:
    """Drop repo_files then analysis_runs (FK 逆順). pgvector 拡張は他で利用されうるため drop しない。"""
    op.drop_index(op.f("ix_repo_files_run_id"), table_name="repo_files")
    op.drop_table("repo_files")
    op.drop_index(op.f("ix_analysis_runs_status"), table_name="analysis_runs")
    op.drop_index(op.f("ix_analysis_runs_job_id"), table_name="analysis_runs")
    op.drop_index(op.f("ix_analysis_runs_kind"), table_name="analysis_runs")
    op.drop_index(op.f("ix_analysis_runs_commit_sha"), table_name="analysis_runs")
    op.drop_index(op.f("ix_analysis_runs_project_id"), table_name="analysis_runs")
    op.drop_table("analysis_runs")
