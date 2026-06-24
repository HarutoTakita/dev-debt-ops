"""GitHub repository integration API."""

from collections.abc import AsyncGenerator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select as sa_select

from app.api.deps import CurrentUser, SASessionDep, get_github_app_service
from app.core.config import settings
from app.models.oauth_account import OAuthAccount
from app.services.github_app import GitHubAppService
from app.services.github_git_client import GitHubGitClient

router = APIRouter(prefix="/github", tags=["GitHub"])

_GH_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RepositoryOut(BaseModel):
    """Repository summary returned by the API."""

    owner: str
    name: str
    full_name: str
    default_branch: str
    private: bool
    updated_at: str


class RepositoryListOut(BaseModel):
    """Paginated repository list."""

    repositories: list[RepositoryOut]
    page: int
    has_more: bool
    app_slug: str = ""  # GitHub App のスラッグ。未グラントの repo を追加する導線（installations/new）に使う


class BranchOut(BaseModel):
    """Branch information."""

    name: str
    is_default: bool


class BranchListOut(BaseModel):
    """List of branches for a repository."""

    branches: list[BranchOut]


class TreeItemOut(BaseModel):
    """Single entry in a repository file tree."""

    path: str
    type: str
    size: int | None = None


class TreeOut(BaseModel):
    """Recursive file tree for a repository branch."""

    tree: list[TreeItemOut]
    branch: str
    truncated: bool


class FileContentOut(BaseModel):
    """File content from a repository."""

    path: str
    content: str | None
    sha: str
    size: int


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


async def resolve_installation_id(
    current_user: CurrentUser,
    session: SASessionDep,
    github_app: Annotated[GitHubAppService, Depends(get_github_app_service)],
) -> int:
    """Resolve the GitHub App installation id for the current user's account.

    Shared by ``resolve_github_client`` (which then mints a token) and the async
    ``analyze-stack`` route (issue 018, method B — only the ``installation_id`` is enqueued
    and the ``service`` container mints the token itself).
    """
    result = await session.execute(
        sa_select(OAuthAccount).where(
            OAuthAccount.user_id == current_user.id,
            OAuthAccount.oauth_name == "github",  # ty: ignore[invalid-argument-type]
        )
    )
    oauth_account = result.scalar_one_or_none()
    if not oauth_account:
        raise HTTPException(status_code=401, detail="GitHub account not connected")

    async with httpx.AsyncClient() as http_client:
        user_resp = await http_client.get(
            "https://api.github.com/user",
            headers={**_GH_HEADERS, "Authorization": f"Bearer {oauth_account.access_token}"},
        )
        if not user_resp.is_success:
            raise HTTPException(status_code=401, detail="GitHub token expired or invalid")
        github_login: str = user_resp.json()["login"]

    try:
        return await github_app.get_installation_for_user(github_login)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail={"reason": "app_not_installed", "app_slug": settings.GITHUB_APP_SLUG},
            ) from e
        raise HTTPException(status_code=502, detail="GitHub API error") from e


InstallationIdDep = Annotated[int, Depends(resolve_installation_id)]


async def resolve_github_client(
    github_app: Annotated[GitHubAppService, Depends(get_github_app_service)],
    installation_id: InstallationIdDep,
) -> AsyncGenerator[GitHubGitClient]:
    """Yield a GitHubGitClient authenticated with the user's GitHub App installation token."""
    token = await github_app.get_installation_token(installation_id)
    client = GitHubGitClient(access_token=token)
    try:
        yield client
    finally:
        await client.aclose()


GitHubClientDep = Annotated[GitHubGitClient, Depends(resolve_github_client)]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/repositories", response_model=RepositoryListOut, summary="リポジトリ一覧")
async def list_repositories(
    client: GitHubClientDep,
    page: int = 1,
    per_page: int = 30,
) -> RepositoryListOut:
    """Return a paginated list of repositories accessible via the GitHub App installation."""
    try:
        result = await client.list_repositories(page=page, per_page=per_page)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="GitHub API error") from e
    has_more = page * per_page < result.total_count
    return RepositoryListOut(
        repositories=[
            RepositoryOut(
                owner=r.owner,
                name=r.name,
                full_name=r.full_name,
                default_branch=r.default_branch,
                private=r.private,
                updated_at=r.updated_at,
            )
            for r in result.repositories
        ],
        page=page,
        has_more=has_more,
        app_slug=settings.GITHUB_APP_SLUG,
    )


@router.get(
    "/repositories/{owner}/{repo}/branches",
    response_model=BranchListOut,
    summary="ブランチ一覧",
)
async def list_branches(
    owner: str,
    repo: str,
    client: GitHubClientDep,
) -> BranchListOut:
    """Return all branches for a repository, marking the default branch."""
    try:
        branches = await client.list_branches(owner, repo)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="GitHub API error") from e
    return BranchListOut(branches=[BranchOut(name=b.name, is_default=b.is_default) for b in branches])


@router.get(
    "/repositories/{owner}/{repo}/tree",
    response_model=TreeOut,
    summary="ファイルツリー(再帰)",
)
async def get_repository_tree(
    owner: str,
    repo: str,
    client: GitHubClientDep,
    branch: str = "main",
) -> TreeOut:
    """Return the recursive file tree for a repository branch."""
    try:
        items = await client.get_repository_tree(owner, repo, branch)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="GitHub API error") from e
    return TreeOut(
        tree=[TreeItemOut(path=i.path, type=i.type, size=i.size) for i in items],
        branch=branch,
        truncated=False,
    )


@router.get(
    "/repositories/{owner}/{repo}/contents",
    response_model=FileContentOut,
    summary="ファイル内容",
)
async def get_file_content(
    owner: str,
    repo: str,
    client: GitHubClientDep,
    path: str = "",
    ref: str = "main",
) -> FileContentOut:
    """Return the decoded content of a file in the repository."""
    if not path:
        raise HTTPException(status_code=422, detail="path is required")
    try:
        fc = await client.get_file_content(owner, repo, path, ref)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="GitHub API error") from e
    return FileContentOut(path=fc.path, content=fc.content, sha=fc.sha, size=fc.size)
