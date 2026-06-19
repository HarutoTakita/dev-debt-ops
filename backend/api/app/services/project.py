import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_async_session
from app.core.exceptions import ConflictError, NotFoundError
from app.models.org import Org
from app.models.project import RESERVED_PROJECT_SLUGS, Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate


def _slugify(value: str) -> str:
    """Derive a URL-safe base slug from arbitrary text. Falls back to 'project' when empty."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


class ProjectService:
    """Business logic for projects (repository-scoped workspaces within an org).

    Route handlers stay thin: they resolve the org scope, verify repository access via
    the GitHub client, then delegate slug/uniqueness rules and persistence to this service.
    """

    def __init__(self, session: Annotated[AsyncSession, Depends(get_async_session)]) -> None:
        self.session = session

    async def list_for_org(self, org: Org) -> list[Project]:
        """Return every active project in the org, newest first (UUIDv7 ids are time-ordered)."""
        result = await self.session.exec(
            select(Project)
            .where(Project.org_id == org.id, col(Project.deleted_at).is_(None))
            .order_by(col(Project.created_at).desc())
        )
        return list(result.all())

    async def get_by_slug(self, org: Org, slug: str) -> Project:
        """Return the active project with the given slug in the org.

        Raises:
            NotFoundError: If no active project with that slug exists in the org.
        """
        result = await self.session.exec(
            select(Project).where(
                Project.org_id == org.id,
                Project.slug == slug,
                col(Project.deleted_at).is_(None),
            )
        )
        project = result.first()
        if not project:
            raise NotFoundError("Project not found")
        return project

    async def _slug_taken(self, org: Org, slug: str) -> bool:
        result = await self.session.exec(
            select(Project.id).where(
                Project.org_id == org.id,
                Project.slug == slug,
                col(Project.deleted_at).is_(None),
            )
        )
        return result.first() is not None

    async def _resolve_unique_slug(self, org: Org, base: str) -> str:
        """Return `base`, or `base-2`, `base-3`, … until a free, non-reserved slug is found."""
        candidate = base
        suffix = 2
        while candidate in RESERVED_PROJECT_SLUGS or await self._slug_taken(org, candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    async def create(self, org: Org, user: User, body: ProjectCreate, github_repo_id: int | None = None) -> Project:
        """Create a project bound to a single repository.

        When `body.slug` is omitted, a unique slug is derived from `body.name`. When an
        explicit slug is given, it must be free; the bound repository must not already be
        connected to another active project in the org.

        Raises:
            ConflictError: If the explicit slug is taken, or the repository is already connected.
        """
        # One repository per project (within the org) — fail fast with a clear message.
        repo_exists = await self.session.exec(
            select(Project.id).where(
                Project.org_id == org.id,
                Project.repo_full_name == body.repo_full_name,
                col(Project.deleted_at).is_(None),
            )
        )
        if repo_exists.first() is not None:
            raise ConflictError("Repository is already connected to a project")

        if body.slug is not None:
            if body.slug in RESERVED_PROJECT_SLUGS:
                raise ConflictError(f"'{body.slug}' is a reserved slug")
            if await self._slug_taken(org, body.slug):
                raise ConflictError("Slug already in use")
            slug = body.slug
        else:
            slug = await self._resolve_unique_slug(org, _slugify(body.name))

        project = Project(
            org_id=org.id,
            name=body.name,
            slug=slug,
            repo_owner=body.repo_owner,
            repo_name=body.repo_name,
            repo_full_name=body.repo_full_name,
            default_branch=body.default_branch,
            repo_private=body.repo_private,
            github_repo_id=github_repo_id,
            created_by=user.id,
        )
        self.session.add(project)
        try:
            await self.session.commit()
        except IntegrityError:
            # Backstop for races against the partial unique indexes.
            await self.session.rollback()
            raise ConflictError("Slug or repository already in use") from None
        await self.session.refresh(project)
        return project

    async def update(self, org: Org, project: Project, body: ProjectUpdate) -> Project:
        """Patch mutable fields on a project (name / slug / default_branch).

        Raises:
            ConflictError: If the new slug is reserved or already in use by another project.
        """
        if body.name is not None:
            project.name = body.name
        if body.default_branch is not None:
            project.default_branch = body.default_branch
        if body.slug is not None and body.slug != project.slug:
            if body.slug in RESERVED_PROJECT_SLUGS:
                raise ConflictError(f"'{body.slug}' is a reserved slug")
            if await self._slug_taken(org, body.slug):
                raise ConflictError("Slug already in use")
            project.slug = body.slug

        self.session.add(project)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError("Slug already in use") from None
        await self.session.refresh(project)
        return project

    async def delete(self, project: Project) -> None:
        """Soft-delete the project."""
        project.deleted_at = datetime.now(UTC)
        self.session.add(project)
        await self.session.commit()


ProjectServiceDep = Annotated[ProjectService, Depends(ProjectService)]
