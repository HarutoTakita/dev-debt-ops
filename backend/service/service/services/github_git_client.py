"""GitHub REST API client authenticated with an installation access token."""

import asyncio
import base64
import logging
import os
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from shared.worker import TransientTaskError

logger = logging.getLogger(__name__)

# Transient GitHub server errors worth retrying (502/503/504). GitHub's Contents API 502s
# intermittently; a single 502 in a many-file backbone loop must not fail the whole analysis step.
_RETRYABLE_STATUS = frozenset({502, 503, 504})
_MAX_RETRIES = 3  # total GET attempts = 1 + _MAX_RETRIES


class _RetryTransport(httpx.AsyncBaseTransport):
    """Retry idempotent GETs on transient GitHub 5xx (502/503/504) with jittered backoff.

    Only GET is retried (safe to replay; no request body to re-stream). Non-GET methods and non-5xx
    responses pass through untouched. 429 / secondary-403 are left to the ``_raise_on_rate_limit``
    response hook (whole-job retry via Cloud Tasks), so this only absorbs transient server blips.
    """

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        if request.method != "GET":
            return response
        for attempt in range(_MAX_RETRIES):
            if response.status_code not in _RETRYABLE_STATUS:
                return response
            await response.aclose()
            await asyncio.sleep(min(0.5 * 2**attempt, 8.0) + random.uniform(0, 0.3))
            response = await self._inner.handle_async_request(request)
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


class _InstallationTokenAuth(httpx.Auth):
    """httpx auth that re-mints the GitHub installation token on a 401 and replays once (issue 078-D).

    GitHub installation tokens expire after ~1h; a long analysis run (clone + agent + backbone +
    per-feature generation) can outlive one, after which every request 401s on a frozen ``Authorization``
    header. This sets the Bearer header from the current token and, on a 401, awaits ``provider`` for a
    fresh token and replays the request once.
    """

    def __init__(self, token: str, provider: Callable[[], Awaitable[str]]) -> None:
        self._token = token
        self._provider = provider

    async def async_auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        response = yield request
        if response.status_code == 401:
            self._token = await self._provider()
            request.headers["Authorization"] = f"Bearer {self._token}"
            yield request


API_BASE = "https://api.github.com"


def _decode_text(raw: bytes) -> str | None:
    """Decode file bytes to text, or ``None`` for genuinely binary content (issue 078-F).

    NUL bytes ⇒ binary ⇒ ``None``. Otherwise decode UTF-8, falling back to a lenient replace so
    non-UTF-8 text (latin-1 / UTF-16-ish) is recovered rather than silently dropped.
    """
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


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

    def __init__(self, access_token: str, *, token_provider: Callable[[], Awaitable[str]] | None = None) -> None:
        """Initialize the client with a GitHub installation access token.

        When ``token_provider`` is given, the token is refreshed on a 401 and the request replayed
        (issue 078-D) — for long runs that can outlive the ~1h installation-token TTL. Without it the
        token is a static header (unchanged behaviour).
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        auth: httpx.Auth | None = None
        if token_provider is not None:
            auth = _InstallationTokenAuth(access_token, token_provider)
        else:
            headers["Authorization"] = f"Bearer {access_token}"
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers=headers,
            auth=auth,
            timeout=30.0,
            transport=_RetryTransport(),  # retry transient 5xx GETs (GitHub Contents API 502s intermittently)
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
        items = [
            TreeItem(
                path=item["path"],
                type=item["type"],
                size=item.get("size"),
            )
            for item in data.get("tree", [])
            if item["type"] in ("blob", "tree")
        ]
        # GitHub silently omits entries and sets truncated=true past ~100k entries / 7MB (issue 078-E).
        # Surface it so a partial file list is visible rather than looking like "these files don't exist".
        if data.get("truncated"):
            logger.warning(
                "GitHub tree truncated for %s/%s@%s — analysis sees a partial file list (%d entries)",
                owner,
                repo,
                branch,
                len(items),
            )
        return items

    async def _fetch_raw_text(self, owner: str, repo: str, path: str, ref: str) -> str | None:
        """Fetch a file's raw bytes (Contents API raw media type) and decode as text, or None if binary.

        Used for files the JSON Contents API won't inline (>1MB come back with ``encoding: "none"``).
        """
        try:
            resp = await self._client.get(
                f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": ref},
                headers={"Accept": "application/vnd.github.raw"},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        return _decode_text(resp.content)

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> FileContent:
        """Return the decoded file content; binary content is returned with content=None.

        Recovers non-UTF-8 text (lenient decode) and >1MB files (which the Contents API returns with
        ``encoding: "none"`` and empty content — fetched via the raw media type), issue 078-F.
        """
        resp = await self._client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
        )
        resp.raise_for_status()
        data = resp.json()

        content: str | None = None
        if data.get("encoding") == "base64" and data.get("content"):
            content = _decode_text(base64.b64decode(data["content"]))
        elif data.get("type") == "file" and data.get("size", 0) > 0:
            # Not inlined (oversize) → fetch the raw bytes instead of silently dropping the file.
            content = await self._fetch_raw_text(owner, repo, path, ref)

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
        """Return the reviews on a pull request (state + reviewer login).

        A 404 is treated as "no reviews" (empty list): the number can refer to an issue or a
        deleted / cross-repo PR surfaced by the commit→PR association, and a single missing PR
        must not abort knowledge-debt detection (issue: knowledge_debt_detection の 404 クラッシュ)。
        """
        resp = await self._client.get(f"/repos/{owner}/{repo}/pulls/{number}/reviews")
        if resp.status_code == 404:
            return []
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


class CachingGitHubGitClient(GitHubGitClient):
    """A ``GitHubGitClient`` that memoises read-only tree/file fetches for one analysis job.

    The agentic backbone runs several sub-pipelines that each fetch the SAME repository tree and
    overlapping file contents (feature clustering / code-debt / KC / knowledge-debt / stack all call
    ``get_repository_tree``, and three of them re-read source files). Sharing ONE of these across the
    backbone collapses those redundant GitHub reads (tree N×→1, files deduped) — a wall-clock + rate
    limit win with no concurrency change (the backbone stays serial, so a plain dict memo suffices).

    Only the hot read paths are cached. Callers treat the returned tree/``FileContent`` as read-only
    (they iterate / read ``.content``); do not mutate them, as the same objects are shared.
    """

    def __init__(self, access_token: str, *, token_provider: Callable[[], Awaitable[str]] | None = None) -> None:
        super().__init__(access_token=access_token, token_provider=token_provider)
        self._tree_cache: dict[tuple[str, str, str], list[TreeItem]] = {}
        self._file_cache: dict[tuple[str, str, str, str], FileContent] = {}

    async def get_repository_tree(self, owner: str, repo: str, branch: str = "main") -> list[TreeItem]:
        """Return the recursive file tree, cached per ``(owner, repo, branch)`` for the job's lifetime."""
        key = (owner, repo, branch)
        if key not in self._tree_cache:
            self._tree_cache[key] = await super().get_repository_tree(owner, repo, branch)
        return self._tree_cache[key]

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> FileContent:
        """Return a file's content, cached per ``(owner, repo, path, ref)`` for the job's lifetime."""
        key = (owner, repo, path, ref)
        if key not in self._file_cache:
            self._file_cache[key] = await super().get_file_content(owner, repo, path, ref)
        return self._file_cache[key]


class LocalCloneGitHubClient(CachingGitHubGitClient):
    """Serve tree + file reads from a local clone; delegate history (blame / commits / PRs) to the API.

    The agentic orchestrator already shallow-clones the repo for the agent / CGC. Reusing that clone
    for the backbone's O(files) ``get_repository_tree`` + ``get_file_content`` reads removes ~all
    Contents-API (REST) calls — the transient-502 source and the dominant REST rate-limit cost — with
    zero extra network I/O. ``get_blame`` / ``list_commits`` stay on the API: a ``--depth 1`` clone has
    no history to serve them, and blame runs on GitHub's *separate* GraphQL budget. Token/auth plumbing
    and every non-file method are inherited unchanged, so a standalone (clone-less) run keeps using the
    plain caching client.

    The local tree is path-sorted (files only); consumers filter ``type == "blob"`` and cap the list,
    so this yields the same files/criteria as the API — only the pre-cap ordering can differ slightly.
    """

    def __init__(
        self, repo_dir: str, *, access_token: str, token_provider: Callable[[], Awaitable[str]] | None = None
    ) -> None:
        super().__init__(access_token=access_token, token_provider=token_provider)
        self._repo_dir = Path(repo_dir).resolve()

    async def get_repository_tree(self, owner: str, repo: str, branch: str = "main") -> list[TreeItem]:
        """Walk the clone and return its files as blob ``TreeItem``s (``.git`` pruned), path-sorted."""
        items: list[TreeItem] = []
        for root, dirs, files in os.walk(self._repo_dir):
            dirs[:] = [d for d in dirs if d != ".git"]  # never descend into git metadata
            for name in files:
                full = Path(root) / name
                if not full.is_file():  # skip broken/dangling symlinks
                    continue
                rel = full.relative_to(self._repo_dir).as_posix()
                items.append(TreeItem(path=rel, type="blob", size=full.stat().st_size))
        items.sort(key=lambda t: t.path)  # deterministic order (API returns git-tree order)
        return items

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> FileContent:
        """Read the file from the clone; binary → ``content=None`` (same lenient decode as the API path).

        Paths outside the clone (``..`` traversal) or missing files return ``content=None`` rather than
        raising — matching how the backbone treats an unreadable file.
        """
        target = (self._repo_dir / path).resolve()
        if not target.is_relative_to(self._repo_dir) or not target.is_file():
            return FileContent(path=path, content=None, sha="", size=0)
        raw = target.read_bytes()
        return FileContent(path=path, content=_decode_text(raw), sha="", size=len(raw))
