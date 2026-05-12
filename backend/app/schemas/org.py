import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.org import OrgRole


class OrgCreate(BaseModel):
    """Request body for creating a new org."""

    name: str = Field(min_length=1, max_length=100, description="Human-readable display name of the org.")
    slug: str = Field(
        min_length=3,
        max_length=48,
        description="URL-safe unique identifier: lowercase alphanumeric characters and single hyphens, "
        "not starting or ending with a hyphen.",
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate that the slug matches the allowed URL-safe format.

        Raises:
            ValueError: If the slug contains uppercase letters, consecutive hyphens,
                or starts/ends with a hyphen.
        """
        if not re.match(r"^[a-z0-9]([a-z0-9]|-(?=[a-z0-9]))*[a-z0-9]$", v):
            raise ValueError("Slug must be lowercase alphanumeric with single hyphens, not starting/ending with hyphen")
        return v


class OrgUpdate(BaseModel):
    """Request body for patching an existing org."""

    name: str | None = Field(
        default=None, min_length=1, max_length=100, description="Human-readable display name of the org."
    )


class OrgRead(BaseModel):
    """Org record as exposed to API clients."""

    id: uuid.UUID = Field(..., description="Unique org identifier.")
    name: str = Field(..., description="Human-readable display name of the org.")
    slug: str = Field(..., description="URL-safe unique identifier used in API paths.")
    is_personal: bool = Field(..., description="True for the auto-created personal org tied to a single user.")
    created_by: uuid.UUID = Field(..., description="ID of the user who created this org.")
    created_at: datetime = Field(..., description="Timestamp when the org was created.")

    model_config = ConfigDict(from_attributes=True)


class OrgMemberUser(BaseModel):
    """Nested user summary embedded in `OrgMemberRead`."""

    id: uuid.UUID = Field(..., description="User ID of the member.")
    email: EmailStr = Field(..., description="User's login email.")
    display_name: str | None = Field(default=None, description="User's preferred display name; NULL when unset.")
    last_active_at: datetime | None = Field(
        default=None, description="UTC timestamp of the user's most recent login; NULL if never updated."
    )
    is_active: bool = Field(default=True, description="Whether the user account is enabled for login.")


class OrgMemberRead(BaseModel):
    """Org membership record as exposed to API clients."""

    id: uuid.UUID = Field(..., description="Unique membership identifier.")
    user_id: uuid.UUID = Field(..., description="ID of the member user.")
    org_id: uuid.UUID = Field(..., description="ID of the org.")
    role: OrgRole = Field(..., description="Role assigned to this member within the org.")
    created_at: datetime = Field(..., description="Timestamp when the membership was created.")
    user: OrgMemberUser = Field(..., description="Nested user summary for display purposes.")

    model_config = ConfigDict(from_attributes=True)


class OrgMemberInvite(BaseModel):
    """Request body for inviting a user to an org by email."""

    email: EmailStr = Field(..., description="Email of the existing user to invite as a MEMBER.")


class OrgMemberRoleUpdate(BaseModel):
    """Request body for changing a member's role within an org."""

    role: OrgRole = Field(..., description="New role to assign to the target member.")
