"""add oauth_accounts table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create oauth_accounts table."""
    op.create_table(
        "oauth_accounts",
        sa.Column("id", GUID, nullable=False),
        sa.Column("oauth_name", sa.String(length=100), nullable=False),
        sa.Column("access_token", sa.String(length=1024), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("refresh_token", sa.String(length=1024), nullable=True),
        sa.Column("account_id", sa.String(length=320), nullable=False),
        sa.Column("account_email", sa.String(length=320), nullable=False),
        sa.Column("user_id", GUID, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_oauth_accounts_user_id_users"), ondelete="cascade"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_accounts")),
    )
    op.create_index(op.f("ix_oauth_accounts_account_id"), "oauth_accounts", ["account_id"], unique=False)
    op.create_index(op.f("ix_oauth_accounts_oauth_name"), "oauth_accounts", ["oauth_name"], unique=False)


def downgrade() -> None:
    """Drop oauth_accounts table."""
    op.drop_index(op.f("ix_oauth_accounts_oauth_name"), table_name="oauth_accounts")
    op.drop_index(op.f("ix_oauth_accounts_account_id"), table_name="oauth_accounts")
    op.drop_table("oauth_accounts")
