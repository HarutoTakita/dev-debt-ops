"""issue 033: GitHubGitClient write methods (branch / file / PR) — httpx mocked."""

from unittest.mock import AsyncMock, MagicMock

from service.services.github_git_client import GitHubGitClient


def _client(json_data: object, *, method: str) -> tuple[GitHubGitClient, MagicMock]:
    response = MagicMock()
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    client = GitHubGitClient(access_token="t")
    client._client = AsyncMock()
    call = AsyncMock(return_value=response)
    setattr(client._client, method, call)
    return client, call


async def test_get_branch_sha() -> None:
    client, _ = _client({"object": {"sha": "abc123"}}, method="get")
    assert await client.get_branch_sha("o", "r", "main") == "abc123"


async def test_create_branch_posts_ref() -> None:
    client, post = _client({}, method="post")
    await client.create_branch("o", "r", "feature/x", "abc123")
    _, kwargs = post.call_args
    assert kwargs["json"] == {"ref": "refs/heads/feature/x", "sha": "abc123"}


async def test_create_or_update_file_base64_encodes() -> None:
    client, put = _client({}, method="put")
    await client.create_or_update_file("o", "r", "src/a.py", message="m", content="hello", branch="b", sha="s")
    _, kwargs = put.call_args
    body = kwargs["json"]
    assert body["branch"] == "b"
    assert body["sha"] == "s"
    # content is base64 of "hello"
    assert body["content"] == "aGVsbG8="


async def test_create_pull_request_returns_number_and_url() -> None:
    client, _ = _client({"number": 42, "html_url": "https://github.com/o/r/pull/42"}, method="post")
    number, url = await client.create_pull_request("o", "r", title="T", head="h", base="main", body="B")
    assert number == 42
    assert url == "https://github.com/o/r/pull/42"
