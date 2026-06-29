"""GitHub REST API client authenticated with an installation access token."""

import base64
from dataclasses import dataclass

import httpx

API_BASE = "https://api.github.com"


@dataclass
class RepositoryInfo:
    """Repository base information."""

    owner: str
    name: str
    full_name: str
    description: str
    url: str
    default_branch: str
    private: bool
    updated_at: str
    repo_id: int | None = None


@dataclass
class RepositoryListResult:
    """Return type for list_repositories."""

    repositories: list["RepositoryInfo"]
    total_count: int


@dataclass
class BranchInfo:
    """Branch information."""

    name: str
    is_default: bool


@dataclass
class TreeItem:
    """Single entry in a file tree."""

    path: str
    type: str  # "blob" | "tree"
    size: int | None


@dataclass
class FileContent:
    """File content retrieved from a repository."""

    path: str
    content: str | None
    sha: str
    size: int


class GitHubGitClient:
    """GitHub REST API client that authenticates with an installation access token."""

    def __init__(self, access_token: str) -> None:
        """Initialize the client with the given GitHub installation access token."""
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def list_repositories(self, page: int = 1, per_page: int = 30) -> RepositoryListResult:
        """Return repositories accessible via the GitHub App installation."""
        per_page = min(per_page, 100)
        resp = await self._client.get(
            "/installation/repositories",
            params={"per_page": per_page, "page": page},
        )
        resp.raise_for_status()
        data = resp.json()
        repositories = [
            RepositoryInfo(
                owner=r["owner"]["login"],
                name=r["name"],
                full_name=r["full_name"],
                description=r.get("description") or "",
                url=r["html_url"],
                default_branch=r.get("default_branch", "main"),
                private=r["private"],
                updated_at=r.get("pushed_at") or r.get("updated_at", ""),
                repo_id=r.get("id"),
            )
            for r in data.get("repositories", [])
        ]
        return RepositoryListResult(repositories=repositories, total_count=data.get("total_count", len(repositories)))

    async def get_repository(self, owner: str, repo: str) -> RepositoryInfo:
        """Return base information for a single repository, raising on inaccessible/missing repos."""
        resp = await self._client.get(f"/repos/{owner}/{repo}")
        resp.raise_for_status()
        r = resp.json()
        return RepositoryInfo(
            owner=r["owner"]["login"],
            name=r["name"],
            full_name=r["full_name"],
            description=r.get("description") or "",
            url=r["html_url"],
            default_branch=r.get("default_branch", "main"),
            private=r["private"],
            updated_at=r.get("pushed_at") or r.get("updated_at", ""),
            repo_id=r.get("id"),
        )

    async def list_branches(self, owner: str, repo: str) -> list[BranchInfo]:
        """Return all branches for a repository, marking the default branch."""
        branches: list[BranchInfo] = []
        page = 1
        while True:
            resp = await self._client.get(
                f"/repos/{owner}/{repo}/branches",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            branches.extend(BranchInfo(name=b["name"], is_default=False) for b in items)
            if len(items) < 100:
                break
            page += 1

        repo_resp = await self._client.get(f"/repos/{owner}/{repo}")
        if repo_resp.is_success:
            default_branch = repo_resp.json().get("default_branch", "main")
            for b in branches:
                if b.name == default_branch:
                    b.is_default = True
                    break

        return branches

    async def get_repository_tree(self, owner: str, repo: str, branch: str = "main") -> list[TreeItem]:
        """Return the recursive file tree for a repository branch."""
        resp = await self._client.get(
            f"/repos/{owner}/{repo}/git/trees/{branch}",
            params={"recursive": "1"},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            TreeItem(
                path=item["path"],
                type=item["type"],
                size=item.get("size"),
            )
            for item in data.get("tree", [])
            if item["type"] in ("blob", "tree")
        ]

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> FileContent:
        """Return the decoded file content; binary files are returned with content=None."""
        resp = await self._client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
        )
        resp.raise_for_status()
        data = resp.json()

        content: str | None = None
        if data.get("encoding") == "base64" and data.get("content"):
            try:
                content = base64.b64decode(data["content"]).decode("utf-8")
            except (UnicodeDecodeError, ValueError):
                content = None

        return FileContent(
            path=data["path"],
            content=content,
            sha=data["sha"],
            size=data.get("size", 0),
        )

    async def create_issue(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        body: str,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
    ) -> tuple[int, str]:
        """Create a GitHub issue and return ``(number, html_url)``.

        「人に頼む」返済経路（issue 210）で使う。assignees がリポジトリのコラボレーターでない場合 GitHub は
        その指定を黙って無視する（issue 自体は作成される）ため、ここでは失敗扱いにしない。
        """
        payload: dict[str, object] = {"title": title, "body": body}
        if assignees:
            payload["assignees"] = assignees
        if labels:
            payload["labels"] = labels
        resp = await self._client.post(f"/repos/{owner}/{repo}/issues", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["number"], data["html_url"]

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
