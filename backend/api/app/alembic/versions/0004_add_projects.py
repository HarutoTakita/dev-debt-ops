"""add projects table

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create projects table with partial unique indexes for slug and repository binding."""
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("repo_owner", sa.String(), nullable=False),
        sa.Column("repo_name", sa.String(), nullable=False),
        sa.Column("repo_full_name", sa.String(), nullable=False),
        sa.Column("default_branch", sa.String(), nullable=False),
        sa.Column("repo_private", sa.Boolean(), nullable=False),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], name=op.f("fk_projects_org_id_orgs")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_projects_created_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_org_id"), "projects", ["org_id"], unique=False)
    op.create_index(op.f("ix_projects_created_by"), "projects", ["created_by"], unique=False)
    op.create_index(
        "uq_projects_org_slug_active",
        "projects",
        ["org_id", "slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_projects_org_repo_active",
        "projects",
        ["org_id", "repo_full_name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Drop projects table and its indexes."""
    op.drop_index("uq_projects_org_repo_active", table_name="projects")
    op.drop_index("uq_projects_org_slug_active", table_name="projects")
    op.drop_index(op.f("ix_projects_created_by"), table_name="projects")
    op.drop_index(op.f("ix_projects_org_id"), table_name="projects")
    op.drop_table("projects")
