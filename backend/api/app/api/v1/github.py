"""GitHub repository integration API."""

from collections.abc import AsyncGenerator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select as sa_select
from sqlmodel import col

from app.api.deps import CurrentUser, SASessionDep, get_github_app_service
from app.core.config import settings
from app.models.oauth_account import OAuthAccount
from app.models.project import Project
from app.services.github_app import GitHubAppService
from app.services.github_git_client import GitHubGitClient
from shared.models import CodeDebt

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
    # Guest demo users (issue 069) have no GitHub OAuth account and must not reach GitHub.
    # Blocking here gates every GitHub-requiring route (project create, analysis triggers,
    # repo listing/tree/contents, analyze-stack, repayment PR) in one chokepoint.
    if current_user.is_demo:
        raise HTTPException(
            status_code=403,
            detail={"reason": "demo_readonly", "message": "GitHub 連携が必要な操作はデモでは利用できません。"},
        )
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


async def resolve_installation_id_optional(
    current_user: CurrentUser,
    session: SASessionDep,
    github_app: Annotated[GitHubAppService, Depends(get_github_app_service)],
) -> int | None:
    """Like ``resolve_installation_id`` but returns ``None`` for demo users instead of 403.

    Demo quizzes are choice-only and graded offline (no GitHub — issue 069), so quiz submission
    must not be blocked by the GitHub chokepoint. Non-demo users still resolve a real id.
    """
    if current_user.is_demo:
        return None
    return await resolve_installation_id(current_user, session, github_app)


OptionalInstallationIdDep = Annotated[int | None, Depends(resolve_installation_id_optional)]


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


async def resolve_github_client_optional(
    github_app: Annotated[GitHubAppService, Depends(get_github_app_service)],
    current_user: CurrentUser,
    session: SASessionDep,
) -> AsyncGenerator[GitHubGitClient | None]:
    """Yield a GitHub client, or ``None`` for guest-demo users (issue 069).

    The read-only repo-browse routes (repositories / branches / tree / contents) accept this so a
    demo guest gets seeded sample data instead of a 403 — making the "コード改善" file browser and the
    new-project repo picker demoable. Write/analysis routes keep using the strict ``GitHubClientDep``.
    """
    if current_user.is_demo:
        yield None
        return
    installation_id = await resolve_installation_id(current_user, session, github_app)
    token = await github_app.get_installation_token(installation_id)
    client = GitHubGitClient(access_token=token)
    try:
        yield client
    finally:
        await client.aclose()


OptionalGitHubClientDep = Annotated[GitHubGitClient | None, Depends(resolve_github_client_optional)]


# Seeded repositories shown in the new-project picker for guest-demo users (issue 069 — no GitHub).
_DEMO_REPOSITORIES = [
    RepositoryOut(
        owner="devdebtops",
        name="sample-shop",
        full_name="devdebtops/sample-shop",
        default_branch="main",
        private=False,
        updated_at="2026-06-20T09:12:00Z",
    ),
    RepositoryOut(
        owner="devdebtops",
        name="checkout-service",
        full_name="devdebtops/checkout-service",
        default_branch="main",
        private=True,
        updated_at="2026-06-18T14:03:00Z",
    ),
    RepositoryOut(
        owner="devdebtops",
        name="marketing-site",
        full_name="devdebtops/marketing-site",
        default_branch="main",
        private=False,
        updated_at="2026-06-15T08:41:00Z",
    ),
    RepositoryOut(
        owner="devdebtops",
        name="mobile-app",
        full_name="devdebtops/mobile-app",
        default_branch="main",
        private=False,
        updated_at="2026-06-12T19:25:00Z",
    ),
    RepositoryOut(
        owner="devdebtops",
        name="data-pipeline",
        full_name="devdebtops/data-pipeline",
        default_branch="main",
        private=True,
        updated_at="2026-06-09T11:50:00Z",
    ),
]


async def _demo_project(session: SASessionDep, owner: str, repo: str) -> Project | None:
    """Return the project whose repo matches ``owner/repo`` (used to serve seeded demo repo data)."""
    result = await session.execute(
        sa_select(Project).where(col(Project.repo_owner) == owner, col(Project.repo_name) == repo)
    )
    return result.scalars().first()


async def _demo_code_debts(session: SASessionDep, owner: str, repo: str) -> dict[str, CodeDebt]:
    """Return ``file_path -> CodeDebt`` for the demo project's files (the seeded file universe + sources)."""
    project = await _demo_project(session, owner, repo)
    if project is None:
        return {}
    result = await session.execute(sa_select(CodeDebt).where(col(CodeDebt.project_id) == project.id))
    by_path: dict[str, CodeDebt] = {}
    for debt in result.scalars().all():
        by_path.setdefault(debt.file_path, debt)
    return by_path


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/repositories", response_model=RepositoryListOut, summary="リポジトリ一覧")
async def list_repositories(
    client: OptionalGitHubClientDep,
    page: int = 1,
    per_page: int = 30,
) -> RepositoryListOut:
    """Return a paginated list of repositories accessible via the GitHub App installation."""
    if client is None:  # guest demo (issue 069) — seeded sample repos for the new-project picker.
        return RepositoryListOut(repositories=_DEMO_REPOSITORIES, page=1, has_more=False, app_slug="")
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
    client: OptionalGitHubClientDep,
) -> BranchListOut:
    """Return all branches for a repository, marking the default branch."""
    if client is None:  # guest demo — single default branch.
        return BranchListOut(branches=[BranchOut(name="main", is_default=True)])
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
    client: OptionalGitHubClientDep,
    session: SASessionDep,
    branch: str = "main",
) -> TreeOut:
    """Return the recursive file tree for a repository branch."""
    if client is None:  # guest demo — build a blob list from the seeded file universe (file-tree folds dirs).
        by_path = await _demo_code_debts(session, owner, repo)
        return TreeOut(
            tree=[
                TreeItemOut(path=path, type="blob", size=len(debt.code_snippet or "")) for path, debt in by_path.items()
            ],
            branch=branch,
            truncated=False,
        )
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
    client: OptionalGitHubClientDep,
    session: SASessionDep,
    path: str = "",
    ref: str = "main",
) -> FileContentOut:
    """Return the decoded content of a file in the repository."""
    if not path:
        raise HTTPException(status_code=422, detail="path is required")
    if client is None:  # guest demo — serve the seeded snippet for this file.
        by_path = await _demo_code_debts(session, owner, repo)
        debt = by_path.get(path)
        if debt is None or debt.code_snippet is None:
            raise HTTPException(status_code=404, detail="file not found")
        return FileContentOut(path=path, content=debt.code_snippet, sha="demo", size=len(debt.code_snippet))
    try:
        fc = await client.get_file_content(owner, repo, path, ref)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="GitHub API error") from e
    return FileContentOut(path=fc.path, content=fc.content, sha=fc.sha, size=fc.size)
