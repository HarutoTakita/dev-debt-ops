"""add knowledge_debts and assigned_developers tables (issue 030)

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create knowledge_debts and the shared assigned_developers table (issue 030).

    knowledge_debts は code_debts と同様 project_id は索引のみ・run_id FK。assigned_developers は
    code/knowledge 両 debt に判別カラム (debt_kind, debt_id) で紐付く（DB FK は張らない）。
    """
    op.create_table(
        "knowledge_debts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("related_adr", sa.String(), nullable=True),
        sa.Column("code_snippet", sa.String(), nullable=False),
        sa.Column("code_debt_score", sa.Float(), nullable=False),
        sa.Column("knowledge_coverage", sa.Float(), nullable=False),
        sa.Column("ai_generation_prob", sa.Float(), nullable=False),
        sa.Column("estimated_repay_hours", sa.Float(), nullable=False),
        sa.Column("detection_notes", sa.String(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], name=op.f("fk_knowledge_debts_run_id_analysis_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_debts")),
        sa.UniqueConstraint("run_id", "file_path", "reason", name="uq_knowledge_debts_run_file_reason"),
    )
    op.create_index(op.f("ix_knowledge_debts_project_id"), "knowledge_debts", ["project_id"], unique=False)
    op.create_index(op.f("ix_knowledge_debts_run_id"), "knowledge_debts", ["run_id"], unique=False)
    op.create_index(op.f("ix_knowledge_debts_file_path"), "knowledge_debts", ["file_path"], unique=False)

    op.create_table(
        "assigned_developers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("debt_kind", sa.String(), nullable=False),
        sa.Column("debt_id", sa.Uuid(), nullable=False),
        sa.Column("github_handle", sa.String(), nullable=False),
        sa.Column("coverage", sa.Float(), nullable=False),
        sa.Column("certified_via", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assigned_developers")),
        sa.UniqueConstraint("debt_kind", "debt_id", "github_handle", name="uq_assigned_developers_debt_handle"),
    )
    op.create_index(op.f("ix_assigned_developers_debt_kind"), "assigned_developers", ["debt_kind"], unique=False)
    op.create_index(op.f("ix_assigned_developers_debt_id"), "assigned_developers", ["debt_id"], unique=False)


def downgrade() -> None:
    """Drop assigned_developers then knowledge_debts."""
    op.drop_index(op.f("ix_assigned_developers_debt_id"), table_name="assigned_developers")
    op.drop_index(op.f("ix_assigned_developers_debt_kind"), table_name="assigned_developers")
    op.drop_table("assigned_developers")
    op.drop_index(op.f("ix_knowledge_debts_file_path"), table_name="knowledge_debts")
    op.drop_index(op.f("ix_knowledge_debts_run_id"), table_name="knowledge_debts")
    op.drop_index(op.f("ix_knowledge_debts_project_id"), table_name="knowledge_debts")
    op.drop_table("knowledge_debts")
