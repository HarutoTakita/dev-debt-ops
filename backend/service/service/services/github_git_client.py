"""GitHub REST API client authenticated with an installation access token."""

import base64
from dataclasses import dataclass

import httpx

from shared.worker import TransientTaskError

API_BASE = "https://api.github.com"


async def _raise_on_rate_limit(response: httpx.Response) -> None:
    """Response hook: turn a GitHub rate-limit response into a transient error (issue-045).

    A 429, or a 403 carrying ``Retry-After`` / ``x-ratelimit-remaining: 0``, is a rate limit
    (primary or secondary), not a permanent failure. Raising ``TransientTaskError`` makes the
    worker return 503 so Cloud Tasks retries, instead of marking the Job FAILED.
    """
    if response.status_code == 429 or (
        response.status_code == 403
        and (response.headers.get("retry-after") is not None or response.headers.get("x-ratelimit-remaining") == "0")
    ):
        raise TransientTaskError(f"GitHub rate limited (status {response.status_code})")


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


@dataclass
class CommitInfo:
    """A single commit with git-author and (when linked) GitHub-account identity.

    ``author_login`` / ``author_id`` come from the GitHub user node (null for commits
    whose author is not a GitHub user); ``author_email`` / ``authored_at`` come from the
    git author metadata which is always present.
    """

    sha: str
    author_login: str | None
    author_email: str | None
    author_id: int | None
    authored_at: str
    message: str


@dataclass
class BlameRange:
    """A contiguous line range attributed to a single commit/author (GraphQL blame)."""

    start_line: int
    end_line: int
    commit_sha: str
    author_login: str | None
    author_email: str | None
    author_id: int | None


@dataclass
class PullRequestInfo:
    """Pull request merge metadata (for review/auto-approve analysis)."""

    number: int
    merged_at: str | None
    merged_by_login: str | None


@dataclass
class ReviewInfo:
    """A single pull request review (state + reviewer login)."""

    state: str
    author_login: str | None
    submitted_at: str | None


# GraphQL blame query — REST exposes no blame endpoint, so history attribution at the
# line level must go through the GraphQL ``object(expression).blame(path)`` field.
_BLAME_QUERY = """
query($owner: String!, $repo: String!, $ref: String!, $path: String!) {
  repository(owner: $owner, name: $repo) {
    object(expression: $ref) {
      ... on Commit {
        blame(path: $path) {
          ranges {
            startingLine
            endingLine
            commit { oid author { email user { login databaseId } } }
          }
        }
      }
    }
  }
}
"""


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
            event_hooks={"response": [_raise_on_rate_limit]},
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

    async def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        path: str | None = None,
        sha: str | None = None,
        since: str | None = None,
        per_page: int = 100,
        page: int = 1,
    ) -> list[CommitInfo]:
        """Return one page of commits (newest first); pass ``path`` for per-file history.

        Callers paginate by incrementing ``page`` until a short page is returned, mirroring
        the per-page cap convention used by :meth:`list_branches`.
        """
        params: dict[str, str | int] = {"per_page": min(per_page, 100), "page": page}
        if path is not None:
            params["path"] = path
        if sha is not None:
            params["sha"] = sha
        if since is not None:
            params["since"] = since
        resp = await self._client.get(f"/repos/{owner}/{repo}/commits", params=params)
        resp.raise_for_status()
        commits: list[CommitInfo] = []
        for item in resp.json():
            commit = item.get("commit") or {}
            git_author = commit.get("author") or {}
            gh_author = item.get("author") or {}
            commits.append(
                CommitInfo(
                    sha=item["sha"],
                    author_login=gh_author.get("login"),
                    author_email=git_author.get("email"),
                    author_id=gh_author.get("id"),
                    authored_at=git_author.get("date", ""),
                    message=commit.get("message", ""),
                )
            )
        return commits

    async def get_blame(self, owner: str, repo: str, path: str, ref: str = "main") -> list[BlameRange]:
        """Return blame line-ranges via GraphQL (REST has no blame endpoint)."""
        resp = await self._client.post(
            "/graphql",
            json={"query": _BLAME_QUERY, "variables": {"owner": owner, "repo": repo, "ref": ref, "path": path}},
        )
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        repository = data.get("repository") or {}
        obj = repository.get("object") or {}
        blame = obj.get("blame") or {}
        ranges: list[BlameRange] = []
        for r in blame.get("ranges", []):
            commit = r.get("commit") or {}
            author = commit.get("author") or {}
            user = author.get("user") or {}
            ranges.append(
                BlameRange(
                    start_line=r["startingLine"],
                    end_line=r["endingLine"],
                    commit_sha=commit.get("oid", ""),
                    author_login=user.get("login"),
                    author_email=author.get("email"),
                    author_id=user.get("databaseId"),
                )
            )
        return ranges

    async def list_pull_requests(
        self, owner: str, repo: str, *, state: str = "all", per_page: int = 100, page: int = 1
    ) -> list[PullRequestInfo]:
        """Return one page of pull requests with merge metadata."""
        resp = await self._client.get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": min(per_page, 100), "page": page},
        )
        resp.raise_for_status()
        pulls: list[PullRequestInfo] = []
        for pr in resp.json():
            merged_by = pr.get("merged_by") or {}
            pulls.append(
                PullRequestInfo(
                    number=pr["number"],
                    merged_at=pr.get("merged_at"),
                    merged_by_login=merged_by.get("login"),
                )
            )
        return pulls

    async def get_pull_request_reviews(self, owner: str, repo: str, number: int) -> list[ReviewInfo]:
        """Return the reviews on a pull request (state + reviewer login)."""
        resp = await self._client.get(f"/repos/{owner}/{repo}/pulls/{number}/reviews")
        resp.raise_for_status()
        reviews: list[ReviewInfo] = []
        for rv in resp.json():
            user = rv.get("user") or {}
            reviews.append(
                ReviewInfo(
                    state=rv.get("state", ""),
                    author_login=user.get("login"),
                    submitted_at=rv.get("submitted_at"),
                )
            )
        return reviews

    async def list_commit_pulls(self, owner: str, repo: str, sha: str) -> list[int]:
        """Return the PR numbers that contain a given commit (for review attribution).

        ``GET /repos/{owner}/{repo}/commits/{sha}/pulls`` — an empty list means the commit was
        pushed directly (no associated pull request).
        """
        resp = await self._client.get(f"/repos/{owner}/{repo}/commits/{sha}/pulls")
        resp.raise_for_status()
        return [pr["number"] for pr in resp.json() if "number" in pr]

    # --- write methods (issue 033; requires contents:write + pull_requests:write) ---------

    async def get_branch_sha(self, owner: str, repo: str, branch: str) -> str:
        """Return the head commit SHA of a branch."""
        resp = await self._client.get(f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
        resp.raise_for_status()
        return resp.json()["object"]["sha"]

    async def create_branch(self, owner: str, repo: str, new_branch: str, from_sha: str) -> None:
        """Create ``refs/heads/{new_branch}`` pointing at ``from_sha``."""
        resp = await self._client.post(
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{new_branch}", "sha": from_sha},
        )
        resp.raise_for_status()

    async def create_or_update_file(
        self, owner: str, repo: str, path: str, *, message: str, content: str, branch: str, sha: str | None = None
    ) -> None:
        """Create or update a file on ``branch`` (pass ``sha`` of the existing blob to update)."""
        body: dict[str, str] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha is not None:
            body["sha"] = sha
        resp = await self._client.put(f"/repos/{owner}/{repo}/contents/{path}", json=body)
        resp.raise_for_status()

    async def find_open_pull_request(self, owner: str, repo: str, head: str) -> tuple[int, str] | None:
        """Return ``(number, html_url)`` of the open PR for ``head`` branch, or None.

        Used to make repayment-PR generation idempotent under at-least-once redelivery (issue-043):
        a prior partial run may have already opened the PR for ``rosetta/repay-*``.
        """
        resp = await self._client.get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "open", "head": f"{owner}:{head}", "per_page": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return data[0]["number"], data[0]["html_url"]

    async def create_pull_request(
        self, owner: str, repo: str, *, title: str, head: str, base: str, body: str
    ) -> tuple[int, str]:
        """Open a pull request and return ``(number, html_url)``."""
        resp = await self._client.post(
            f"/repos/{owner}/{repo}/pulls",
            json={"title": title, "head": head, "base": base, "body": body},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["number"], data["html_url"]

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
