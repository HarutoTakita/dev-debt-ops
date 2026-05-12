import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import String
from sqlmodel import Field, Relationship, SQLModel

from app.models.base import created_at_field, deleted_at_field, updated_at_field, uuid7_pk


class OrgRole(StrEnum):
    """Member role within an org. Ordered by privilege: OWNER > ADMIN > MEMBER."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


ROLE_HIERARCHY: dict[OrgRole, int] = {OrgRole.OWNER: 3, OrgRole.ADMIN: 2, OrgRole.MEMBER: 1}


class Org(SQLModel, table=True):
    """An organisation, the multitenancy boundary for all resources.

    Orgs are soft-deleted via `deleted_at`; active rows have `deleted_at IS NULL`.
    The `uq_orgs_slug_active` partial unique index (defined in the Alembic migration)
    enforces slug uniqueness only among non-deleted orgs. Each user also has exactly
    one personal org (`is_personal=True`) created automatically on registration.
    """

    __tablename__ = "orgs"

    id: uuid.UUID = uuid7_pk()
    name: str = Field(nullable=False, description="Human-readable display name of the org.")
    slug: str = Field(nullable=False, description="URL-safe unique identifier (lowercase alphanumeric + hyphens).")
    is_personal: bool = Field(
        default=False,
        nullable=False,
        description="True for the auto-created personal org tied to a single user; False for team orgs.",
    )
    created_by: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, index=True, description="User who created this org."
    )
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
    deleted_at: datetime | None = deleted_at_field()

    members: list["OrgMember"] = Relationship(back_populates="org")


class OrgMember(SQLModel, table=True):
    """A user's membership in an org, with an assigned role.

    Memberships are soft-deleted via `deleted_at`; active memberships have `deleted_at IS NULL`.
    """

    __tablename__ = "org_members"

    id: uuid.UUID = uuid7_pk()
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, index=True, description="User who is a member of the org."
    )
    org_id: uuid.UUID = Field(foreign_key="orgs.id", nullable=False, index=True, description="Org the user belongs to.")
    role: OrgRole = Field(
        default=OrgRole.MEMBER,
        nullable=False,
        sa_type=String,
        description="Role assigned to this member within the org.",
    )
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
    deleted_at: datetime | None = deleted_at_field()

    org: Org = Relationship(back_populates="members")
