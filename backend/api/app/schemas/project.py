import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.project import RESERVED_PROJECT_SLUGS

_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9]|-(?=[a-z0-9]))*[a-z0-9]$")


def _validate_slug(v: str) -> str:
    """Validate a project slug: URL-safe format and not a reserved org-level segment.

    Raises:
        ValueError: If the slug is malformed or reserved.
    """
    if not _SLUG_RE.match(v):
        raise ValueError("Slug must be lowercase alphanumeric with single hyphens, not starting/ending with hyphen")
    if v in RESERVED_PROJECT_SLUGS:
        raise ValueError(f"'{v}' is a reserved slug")
    return v


class ProjectCreate(BaseModel):
    """Request body for creating a project. Binds the project to exactly one repository.

    `slug` is optional: when omitted, the service derives a unique slug from `name`.
    """

    name: str = Field(min_length=1, max_length=100, description="Human-readable project name.")
    slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=48,
        description="Optional URL-safe identifier. Auto-derived from name when omitted.",
    )
    repo_owner: str = Field(min_length=1, description="GitHub repository owner (login).")
    repo_name: str = Field(min_length=1, description="GitHub repository name.")
    repo_full_name: str = Field(min_length=1, description="GitHub `owner/name`.")
    default_branch: str = Field(default="main", min_length=1, description="Default branch of the repository.")
    repo_private: bool = Field(default=False, description="Whether the repository is private.")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        """Validate the slug format and reserved-word constraint when one is supplied."""
        return _validate_slug(v) if v is not None else None


class ProjectUpdate(BaseModel):
    """Request body for patching a project. All fields optional (partial update)."""

    name: str | None = Field(default=None, min_length=1, max_length=100, description="New display name.")
    slug: str | None = Field(default=None, min_length=3, max_length=48, description="New URL-safe identifier.")
    default_branch: str | None = Field(default=None, min_length=1, description="New default branch.")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        """Validate the slug format and reserved-word constraint when one is supplied."""
        return _validate_slug(v) if v is not None else None


class ProjectRead(BaseModel):
    """Project record as exposed to API clients."""

    id: uuid.UUID = Field(..., description="Unique project identifier.")
    org_id: uuid.UUID = Field(..., description="ID of the owning org.")
    name: str = Field(..., description="Human-readable project name.")
    slug: str = Field(..., description="URL-safe identifier used in API paths.")
    repo_owner: str = Field(..., description="GitHub repository owner.")
    repo_name: str = Field(..., description="GitHub repository name.")
    repo_full_name: str = Field(..., description="GitHub `owner/name`.")
    default_branch: str = Field(..., description="Default branch of the bound repository.")
    repo_private: bool = Field(..., description="Whether the bound repository is private.")
    github_repo_id: int | None = Field(default=None, description="Stable GitHub repository id, if known.")
    created_by: uuid.UUID = Field(..., description="ID of the user who created the project.")
    created_at: datetime = Field(..., description="Timestamp when the project was created.")

    model_config = ConfigDict(from_attributes=True)


class ProjectListOut(BaseModel):
    """Paginated-free list wrapper, mirroring other list responses."""

    projects: list[ProjectRead] = Field(..., description="Active projects in the org.")
