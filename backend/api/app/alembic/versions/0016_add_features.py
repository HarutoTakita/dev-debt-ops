"""add features / feature_files (issue 052)

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the feature-clustering tables (issue 052). project_id is indexed (no FK)."""
    op.create_table(
        "features",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], name=op.f("fk_features_run_id_analysis_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_features")),
        sa.UniqueConstraint("run_id", "key", name="uq_features_run_key"),
    )
    op.create_index(op.f("ix_features_project_id"), "features", ["project_id"], unique=False)
    op.create_index(op.f("ix_features_run_id"), "features", ["run_id"], unique=False)

    op.create_table(
        "feature_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("feature_id", sa.Uuid(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], name=op.f("fk_feature_files_run_id_analysis_runs")),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], name=op.f("fk_feature_files_feature_id_features")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feature_files")),
        sa.UniqueConstraint("run_id", "feature_id", "file_path", name="uq_feature_files_run_feature_path"),
    )
    op.create_index(op.f("ix_feature_files_run_id"), "feature_files", ["run_id"], unique=False)
    op.create_index(op.f("ix_feature_files_feature_id"), "feature_files", ["feature_id"], unique=False)
    op.create_index(op.f("ix_feature_files_file_path"), "feature_files", ["file_path"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_feature_files_file_path"), table_name="feature_files")
    op.drop_index(op.f("ix_feature_files_feature_id"), table_name="feature_files")
    op.drop_index(op.f("ix_feature_files_run_id"), table_name="feature_files")
    op.drop_table("feature_files")
    op.drop_index(op.f("ix_features_run_id"), table_name="features")
    op.drop_index(op.f("ix_features_project_id"), table_name="features")
    op.drop_table("features")
