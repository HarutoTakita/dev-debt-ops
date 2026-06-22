"""drop agent_pipelines / agent_activities / narrative_steps / narrative_evidence (remove Twin Agent loop)

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-22

The Twin-Agent "loop" (issue 036) summarised agent activity into these tables, surfaced through the
``agents`` API and the analysis-run cockpit's ``loop_agents`` stage. The agents view was abolished
(issue 051) and the cockpit stage removed, leaving the tables without any consumer — so the pipeline,
API and tables are dropped. ``JobType.{CODE_DEBT,KNOWLEDGE_DEBT}_LOOP`` enum values are intentionally
kept so historical ``jobs`` rows still load. The downgrade recreates the tables (mirrors 0013).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the agent-loop tables (FK-reverse order)."""
    op.drop_index(op.f("ix_narrative_evidence_step_id"), table_name="narrative_evidence")
    op.drop_table("narrative_evidence")
    op.drop_index(op.f("ix_narrative_steps_activity_id"), table_name="narrative_steps")
    op.drop_table("narrative_steps")
    op.drop_index(op.f("ix_agent_activities_project_id"), table_name="agent_activities")
    op.drop_table("agent_activities")
    op.drop_index(op.f("ix_agent_pipelines_project_id"), table_name="agent_pipelines")
    op.drop_table("agent_pipelines")


def downgrade() -> None:
    """Recreate the Twin-Agent loop tables (mirrors 0013). project_id is indexed (no FK)."""
    op.create_table(
        "agent_pipelines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_pipelines")),
    )
    op.create_index(op.f("ix_agent_pipelines_project_id"), "agent_pipelines", ["project_id"], unique=False)

    op.create_table(
        "agent_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("headline", sa.String(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["pipeline_id"], ["agent_pipelines.id"], name=op.f("fk_agent_activities_pipeline_id_agent_pipelines")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_activities")),
    )
    op.create_index(op.f("ix_agent_activities_project_id"), "agent_activities", ["project_id"], unique=False)

    op.create_table(
        "narrative_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"], ["agent_activities.id"], name=op.f("fk_narrative_steps_activity_id_agent_activities")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_narrative_steps")),
    )
    op.create_index(op.f("ix_narrative_steps_activity_id"), "narrative_steps", ["activity_id"], unique=False)

    op.create_table(
        "narrative_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("href", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["step_id"], ["narrative_steps.id"], name=op.f("fk_narrative_evidence_step_id_narrative_steps")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_narrative_evidence")),
    )
    op.create_index(op.f("ix_narrative_evidence_step_id"), "narrative_evidence", ["step_id"], unique=False)
