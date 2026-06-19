import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.github import resolve_github_client
from app.main import app
from app.services.github_git_client import RepositoryInfo
from tests.conftest import register_and_login

# Repositories the fake GitHub client "knows about". Anything else 404s.
_REPOS: dict[str, RepositoryInfo] = {
    "acme/web": RepositoryInfo(
        owner="acme",
        name="web",
        full_name="acme/web",
        description="",
        url="https://github.com/acme/web",
        default_branch="main",
        private=True,
        updated_at="2026-06-01T00:00:00Z",
        repo_id=111,
    ),
    "acme/api": RepositoryInfo(
        owner="acme",
        name="api",
        full_name="acme/api",
        description="",
        url="https://github.com/acme/api",
        default_branch="develop",
        private=False,
        updated_at="2026-06-02T00:00:00Z",
        repo_id=222,
    ),
}


class _FakeGitHubClient:
    """Stand-in for GitHubGitClient that resolves repos from a static map."""

    async def get_repository(self, owner: str, repo: str) -> RepositoryInfo:
        info = _REPOS.get(f"{owner}/{repo}")
        if info is None:
            raise httpx.HTTPStatusError(
                "not found",
                request=httpx.Request("GET", f"https://api.github.com/repos/{owner}/{repo}"),
                response=httpx.Response(404),
            )
        return info


@pytest.fixture(autouse=True)
def _override_github():
    """Replace the GitHub client dependency with a fake for all project tests."""
    app.dependency_overrides[resolve_github_client] = lambda: _FakeGitHubClient()
    yield
    app.dependency_overrides.pop(resolve_github_client, None)


async def _create_org(client: AsyncClient, slug: str = "test-org") -> None:
    await client.post("/api/v1/orgs", json={"name": "Test Org", "slug": slug})


def _body(name: str = "Web Frontend", repo: str = "acme/web", **extra) -> dict:
    owner, name_part = repo.split("/")
    return {
        "name": name,
        "repo_owner": owner,
        "repo_name": name_part,
        "repo_full_name": repo,
        **extra,
    }


async def test_create_project(authenticated_client: AsyncClient) -> None:
    await _create_org(authenticated_client)
    response = await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body())
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Web Frontend"
    assert data["slug"] == "web-frontend"
    assert data["repo_full_name"] == "acme/web"
    # canonical metadata comes from GitHub, not the client
    assert data["default_branch"] == "main"
    assert data["repo_private"] is True
    assert data["github_repo_id"] == 111


async def test_list_projects(authenticated_client: AsyncClient) -> None:
    await _create_org(authenticated_client)
    await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body("Web", "acme/web"))
    await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body("API", "acme/api"))
    response = await authenticated_client.get("/api/v1/orgs/test-org/projects")
    assert response.status_code == 200
    projects = response.json()["projects"]
    assert {p["repo_full_name"] for p in projects} == {"acme/web", "acme/api"}


async def test_get_project(authenticated_client: AsyncClient) -> None:
    await _create_org(authenticated_client)
    created = await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body())
    slug = created.json()["slug"]
    response = await authenticated_client.get(f"/api/v1/orgs/test-org/projects/{slug}")
    assert response.status_code == 200
    assert response.json()["repo_full_name"] == "acme/web"


async def test_get_unknown_project_404(authenticated_client: AsyncClient) -> None:
    await _create_org(authenticated_client)
    response = await authenticated_client.get("/api/v1/orgs/test-org/projects/nope")
    assert response.status_code == 404


async def test_duplicate_slug_conflict(authenticated_client: AsyncClient) -> None:
    await _create_org(authenticated_client)
    await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body("Web", "acme/web", slug="shared"))
    response = await authenticated_client.post(
        "/api/v1/orgs/test-org/projects", json=_body("API", "acme/api", slug="shared")
    )
    assert response.status_code == 409


async def test_duplicate_repo_conflict(authenticated_client: AsyncClient) -> None:
    await _create_org(authenticated_client)
    await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body("Web", "acme/web"))
    response = await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body("Web Again", "acme/web"))
    assert response.status_code == 409


async def test_reserved_slug_rejected(authenticated_client: AsyncClient) -> None:
    await _create_org(authenticated_client)
    response = await authenticated_client.post(
        "/api/v1/orgs/test-org/projects", json=_body("Settings", "acme/web", slug="settings")
    )
    assert response.status_code == 422


async def test_nonexistent_repo_rejected(authenticated_client: AsyncClient) -> None:
    await _create_org(authenticated_client)
    response = await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body("Ghost", "acme/ghost"))
    assert response.status_code == 404


async def test_update_project(authenticated_client: AsyncClient) -> None:
    await _create_org(authenticated_client)
    created = await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body())
    slug = created.json()["slug"]
    response = await authenticated_client.patch(
        f"/api/v1/orgs/test-org/projects/{slug}",
        json={"name": "Renamed", "slug": "renamed", "default_branch": "trunk"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Renamed"
    assert data["slug"] == "renamed"
    assert data["default_branch"] == "trunk"


async def test_delete_project_then_reuse_repo(authenticated_client: AsyncClient) -> None:
    await _create_org(authenticated_client)
    created = await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body())
    slug = created.json()["slug"]
    delete = await authenticated_client.delete(f"/api/v1/orgs/test-org/projects/{slug}")
    assert delete.status_code == 204
    # gone
    assert (await authenticated_client.get(f"/api/v1/orgs/test-org/projects/{slug}")).status_code == 404
    # the repo can be connected to a fresh project again (partial unique index excludes soft-deleted)
    recreate = await authenticated_client.post("/api/v1/orgs/test-org/projects", json=_body())
    assert recreate.status_code == 201


async def test_member_cannot_create_project() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner:
        await register_and_login(owner, "owner@example.com")
        await owner.post("/api/v1/orgs", json={"name": "Team", "slug": "team"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as member:
        await register_and_login(member, "member@example.com")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner:
        await register_and_login(owner, "owner@example.com")
        await owner.post("/api/v1/orgs/team/members", json={"email": "member@example.com"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as member:
        await register_and_login(member, "member@example.com")
        response = await member.post("/api/v1/orgs/team/projects", json=_body())
        assert response.status_code == 403
