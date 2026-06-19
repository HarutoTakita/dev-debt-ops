"""Project API — repository-scoped workspaces within an org (1 project == 1 repository)."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Path, status

from app.api.deps import CurrentUser, OrgAdminScope, OrgScope
from app.api.v1.github import GitHubClientDep
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectListOut, ProjectRead, ProjectUpdate
from app.services.project import ProjectServiceDep

router = APIRouter(tags=["projects"])


@router.get(
    "/orgs/{slug}/projects",
    response_model=ProjectListOut,
    summary="List projects in an org",
    response_description="Every active project in the org.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not a member of this org."},
        status.HTTP_404_NOT_FOUND: {"description": "Org not found."},
    },
)
async def list_projects(org_membership: OrgScope, service: ProjectServiceDep) -> ProjectListOut:
    """Return all active projects in the org.

    Raises:
        NotFoundError: If no active org with the given slug exists.
        PermissionDeniedError: If the caller is not an active member.
    """
    org, _ = org_membership
    projects = await service.list_for_org(org)
    return ProjectListOut(projects=[ProjectRead.model_validate(p) for p in projects])


@router.get(
    "/orgs/{slug}/projects/{project_slug}",
    response_model=ProjectRead,
    summary="Get a project",
    response_description="The project record.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not a member of this org."},
        status.HTTP_404_NOT_FOUND: {"description": "Org or project not found."},
    },
)
async def get_project(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgScope,
    service: ProjectServiceDep,
) -> Project:
    """Return a single project by slug.

    Raises:
        NotFoundError: If the org or project does not exist.
        PermissionDeniedError: If the caller is not an active member.
    """
    org, _ = org_membership
    return await service.get_by_slug(org, project_slug)


@router.post(
    "/orgs/{slug}/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project bound to a repository",
    response_description="The newly created project.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not an admin of this org."},
        status.HTTP_404_NOT_FOUND: {"description": "Org or repository not found / not accessible."},
        status.HTTP_409_CONFLICT: {"description": "Slug taken, or repository already connected."},
    },
)
async def create_project(
    body: ProjectCreate,
    org_membership: OrgAdminScope,
    current_user: CurrentUser,
    service: ProjectServiceDep,
    client: GitHubClientDep,
) -> Project:
    """Create a project bound to a single repository, verified via the GitHub App installation.

    The bound repository is confirmed accessible (and its canonical metadata read) before the
    project is persisted. One repository maps to at most one active project per org.

    Raises:
        NotFoundError: If the org or repository is not found / not accessible.
        PermissionDeniedError: If the caller is not an admin of this org.
        BadRequestError: If GitHub cannot be reached to verify the repository.
        ConflictError: If the slug is taken or the repository is already connected.
    """
    org, _ = org_membership
    try:
        repo_info = await client.get_repository(body.repo_owner, body.repo_name)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise NotFoundError("Repository not found or not accessible") from e
        raise BadRequestError("Failed to verify repository with GitHub") from e

    # Trust GitHub's canonical metadata over the client-supplied values.
    body.repo_owner = repo_info.owner
    body.repo_name = repo_info.name
    body.repo_full_name = repo_info.full_name
    body.default_branch = repo_info.default_branch
    body.repo_private = repo_info.private
    return await service.create(org, current_user, body, github_repo_id=repo_info.repo_id)


@router.patch(
    "/orgs/{slug}/projects/{project_slug}",
    response_model=ProjectRead,
    summary="Update a project",
    response_description="The updated project record.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not an admin of this org."},
        status.HTTP_404_NOT_FOUND: {"description": "Org or project not found."},
        status.HTTP_409_CONFLICT: {"description": "Slug already in use."},
    },
)
async def update_project(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    body: ProjectUpdate,
    org_membership: OrgAdminScope,
    service: ProjectServiceDep,
) -> Project:
    """Patch mutable fields (name / slug / default_branch) on a project.

    Raises:
        NotFoundError: If the org or project does not exist.
        PermissionDeniedError: If the caller is not an admin of this org.
        ConflictError: If the new slug is reserved or already in use.
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    return await service.update(org, project, body)


@router.delete(
    "/orgs/{slug}/projects/{project_slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
    response_description="The project is soft-deleted.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not an admin of this org."},
        status.HTTP_404_NOT_FOUND: {"description": "Org or project not found."},
    },
)
async def delete_project(
    project_slug: Annotated[str, Path(description="Project slug within the org.")],
    org_membership: OrgAdminScope,
    service: ProjectServiceDep,
) -> None:
    """Soft-delete a project.

    Raises:
        NotFoundError: If the org or project does not exist.
        PermissionDeniedError: If the caller is not an admin of this org.
    """
    org, _ = org_membership
    project = await service.get_by_slug(org, project_slug)
    await service.delete(project)
