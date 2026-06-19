import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, deleted_at_field, updated_at_field, uuid7_pk

# Slugs reserved by org-level static routes (`/[org]/<segment>`). A project slug must not
# collide with these, otherwise the project would be unreachable behind the static route.
RESERVED_PROJECT_SLUGS: frozenset[str] = frozenset({"settings", "projects", "new", "members"})


class Project(SQLModel, table=True):
    """An observed git repository within an org. Invariant: 1 project == 1 repository.

    Projects are the unit all debt analysis is scoped to. They are soft-deleted via
    `deleted_at`; active rows have `deleted_at IS NULL`. Two partial unique indexes
    (defined in the Alembic migration) enforce, among non-deleted rows scoped to the org:
    `uq_projects_org_slug_active` (slug uniqueness) and `uq_projects_org_repo_active`
    (one project per repository).
    """

    __tablename__ = "projects"

    id: uuid.UUID = uuid7_pk()
    org_id: uuid.UUID = Field(
        foreign_key="orgs.id", nullable=False, index=True, description="Org this project belongs to."
    )
    name: str = Field(nullable=False, description="Human-readable project name.")
    slug: str = Field(nullable=False, description="URL-safe identifier, unique within the org.")
    repo_owner: str = Field(nullable=False, description="GitHub repository owner (login).")
    repo_name: str = Field(nullable=False, description="GitHub repository name.")
    repo_full_name: str = Field(nullable=False, description="GitHub `owner/name`.")
    default_branch: str = Field(default="main", nullable=False, description="Default branch of the bound repository.")
    repo_private: bool = Field(default=False, nullable=False, description="Whether the bound repository is private.")
    github_repo_id: int | None = Field(
        default=None, description="Stable GitHub repository id; survives repository renames."
    )
    created_by: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, index=True, description="User who created this project."
    )
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
    deleted_at: datetime | None = deleted_at_field()
