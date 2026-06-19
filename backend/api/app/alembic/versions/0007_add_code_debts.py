"""add code_debts table (issue 028)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create code_debts (code-debt detection findings, issue 028).

    project_id は AnalysisRun と同じく FK 無し（projects は shared metadata に無い）。
    run_id → analysis_runs.id は FK を張る。一意制約は (run_id, file_path, type)。
    """
    op.create_table(
        "code_debts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("related_pr", sa.String(), nullable=True),
        sa.Column("related_adr", sa.String(), nullable=True),
        sa.Column("archaeology_notes", sa.String(), nullable=False),
        sa.Column("code_snippet", sa.String(), nullable=False),
        sa.Column("code_debt_score", sa.Float(), nullable=False),
        sa.Column("knowledge_coverage", sa.Float(), nullable=False),
        sa.Column("ai_generation_prob", sa.Float(), nullable=False),
        sa.Column("estimated_repay_hours", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], name=op.f("fk_code_debts_run_id_analysis_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_code_debts")),
        sa.UniqueConstraint("run_id", "file_path", "type", name="uq_code_debts_run_file_type"),
    )
    op.create_index(op.f("ix_code_debts_project_id"), "code_debts", ["project_id"], unique=False)
    op.create_index(op.f("ix_code_debts_run_id"), "code_debts", ["run_id"], unique=False)
    op.create_index(op.f("ix_code_debts_file_path"), "code_debts", ["file_path"], unique=False)


def downgrade() -> None:
    """Drop code_debts."""
    op.drop_index(op.f("ix_code_debts_file_path"), table_name="code_debts")
    op.drop_index(op.f("ix_code_debts_run_id"), table_name="code_debts")
    op.drop_index(op.f("ix_code_debts_project_id"), table_name="code_debts")
    op.drop_table("code_debts")
