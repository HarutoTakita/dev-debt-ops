"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-12

"""

from collections.abc import Sequence

import fastapi_users_db_sqlalchemy.generics
import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial schema: users, orgs, org_members, refresh_tokens."""
    op.create_table(
        "users",
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_epoch", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "orgs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("is_personal", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_orgs_created_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orgs")),
    )
    op.create_index(op.f("ix_orgs_created_by"), "orgs", ["created_by"], unique=False)
    op.create_index(
        "uq_orgs_slug_active",
        "orgs",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "org_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], name=op.f("fk_org_members_org_id_orgs")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_org_members_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_members")),
    )
    op.create_index(op.f("ix_org_members_org_id"), "org_members", ["org_id"], unique=False)
    op.create_index(op.f("ix_org_members_user_id"), "org_members", ["user_id"], unique=False)
    op.create_index(
        "uq_org_members_user_org_active",
        "org_members",
        ["user_id", "org_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.execute(
        "ALTER TABLE org_members ADD CONSTRAINT ck_org_members_role CHECK (role IN ('owner', 'admin', 'member'))"
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("token", sa.String(length=43), nullable=False),
        sa.Column(
            "created_at",
            fastapi_users_db_sqlalchemy.generics.TIMESTAMPAware(timezone=True),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_token", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id_users"), ondelete="cascade"
        ),
        sa.PrimaryKeyConstraint("token", name=op.f("pk_refresh_tokens")),
    )
    op.create_index(op.f("ix_refresh_tokens_created_at"), "refresh_tokens", ["created_at"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_expires_at"), "refresh_tokens", ["expires_at"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_family_id"), "refresh_tokens", ["family_id"], unique=False)
    op.create_index(
        "ix_refresh_tokens_user_id_active",
        "refresh_tokens",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("refresh_tokens")
    op.execute("ALTER TABLE org_members DROP CONSTRAINT ck_org_members_role")
    op.drop_index("uq_org_members_user_org_active", table_name="org_members")
    op.drop_index(op.f("ix_org_members_user_id"), table_name="org_members")
    op.drop_index(op.f("ix_org_members_org_id"), table_name="org_members")
    op.drop_table("org_members")
    op.drop_index("uq_orgs_slug_active", table_name="orgs")
    op.drop_index(op.f("ix_orgs_created_by"), table_name="orgs")
    op.drop_table("orgs")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
