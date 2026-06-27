"""add learning_resources / learning_plans / learning_steps tables (issue 035)

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the learning-plan tables (issue 035). project_id is indexed (no FK)."""
    op.create_table(
        "learning_resources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("dormant_days", sa.Integer(), nullable=True),
        sa.Column("origin_meta", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learning_resources")),
    )
    op.create_index(op.f("ix_learning_resources_project_id"), "learning_resources", ["project_id"], unique=False)

    op.create_table(
        "learning_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("gap_concepts", sa.JSON(), nullable=False),
        sa.Column("estimated_total_minutes", sa.Integer(), nullable=False),
        sa.Column("quiz_session_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learning_plans")),
    )
    op.create_index(op.f("ix_learning_plans_project_id"), "learning_plans", ["project_id"], unique=False)

    op.create_table(
        "learning_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["learning_plans.id"], name=op.f("fk_learning_steps_plan_id_learning_plans")
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"], ["learning_resources.id"], name=op.f("fk_learning_steps_resource_id_learning_resources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learning_steps")),
        sa.UniqueConstraint("plan_id", "order", name="uq_learning_steps_plan_order"),
    )
    op.create_index(op.f("ix_learning_steps_plan_id"), "learning_steps", ["plan_id"], unique=False)


def downgrade() -> None:
    """Drop learning_steps, learning_plans, learning_resources (FK-reverse order)."""
    op.drop_index(op.f("ix_learning_steps_plan_id"), table_name="learning_steps")
    op.drop_table("learning_steps")
    op.drop_index(op.f("ix_learning_plans_project_id"), table_name="learning_plans")
    op.drop_table("learning_plans")
    op.drop_index(op.f("ix_learning_resources_project_id"), table_name="learning_resources")
    op.drop_table("learning_resources")
