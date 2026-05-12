"""GitHubGitClient ユニットテスト。

httpx クライアントをモック化し、HTTP 通信なしでレスポンスのマッピングロジックを検証する。
"""

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.github_git_client import FileContent, GitHubGitClient, RepositoryInfo, TreeItem


def _make_client() -> GitHubGitClient:
    """_client をモック化した GitHubGitClient を返す。"""
    client = GitHubGitClient.__new__(GitHubGitClient)
    client._client = AsyncMock()
    return client


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


def _repo_json(**overrides) -> dict:
    base = {
        "owner": {"login": "org"},
        "name": "repo",
        "full_name": "org/repo",
        "description": "A repo",
        "html_url": "https://github.com/org/repo",
        "default_branch": "main",
        "private": False,
        "pushed_at": "2026-01-01T00:00:00Z",
    }
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# list_repositories
# ---------------------------------------------------------------------------


class TestListRepositories:
    async def test_returns_repository_info_list(self):
        client = _make_client()
        client._client.get.return_value = _mock_response(
            {"repositories": [_repo_json()], "total_count": 1}
        )

        repos = await client.list_repositories()

        assert len(repos) == 1
        repo = repos[0]
        assert isinstance(repo, RepositoryInfo)
        assert repo.owner == "org"
        assert repo.name == "repo"
        assert repo.full_name == "org/repo"
        assert repo.url == "https://github.com/org/repo"
        assert repo.default_branch == "main"
        assert repo.private is False

    async def test_empty_repositories_returns_empty_list(self):
        client = _make_client()
        client._client.get.return_value = _mock_response(
            {"repositories": [], "total_count": 0}
        )

        repos = await client.list_repositories()

        assert repos == []

    async def test_per_page_is_capped_at_100(self):
        client = _make_client()
        client._client.get.return_value = _mock_response(
            {"repositories": [], "total_count": 0}
        )

        await client.list_repositories(per_page=200)

        _, kwargs = client._client.get.call_args
        assert kwargs["params"]["per_page"] == 100

    async def test_page_parameter_is_forwarded(self):
        client = _make_client()
        client._client.get.return_value = _mock_response(
            {"repositories": [], "total_count": 0}
        )

        await client.list_repositories(page=3)

        _, kwargs = client._client.get.call_args
        assert kwargs["params"]["page"] == 3

    async def test_null_description_becomes_empty_string(self):
        client = _make_client()
        client._client.get.return_value = _mock_response(
            {"repositories": [_repo_json(description=None)], "total_count": 1}
        )

        repos = await client.list_repositories()

        assert repos[0].description == ""

    async def test_falls_back_to_updated_at_when_pushed_at_missing(self):
        client = _make_client()
        data = _repo_json()
        del data["pushed_at"]
        data["updated_at"] = "2025-06-01T00:00:00Z"
        client._client.get.return_value = _mock_response(
            {"repositories": [data], "total_count": 1}
        )

        repos = await client.list_repositories()

        assert repos[0].updated_at == "2025-06-01T00:00:00Z"


# ---------------------------------------------------------------------------
# get_repository_tree
# ---------------------------------------------------------------------------


class TestGetRepositoryTree:
    async def test_returns_tree_items(self):
        client = _make_client()
        client._client.get.return_value = _mock_response({
            "tree": [
                {"path": "src/index.ts", "type": "blob", "size": 100},
                {"path": "src", "type": "tree", "size": None},
            ],
            "truncated": False,
        })

        items = await client.get_repository_tree("org", "repo")

        assert len(items) == 2
        assert all(isinstance(i, TreeItem) for i in items)
        assert items[0].path == "src/index.ts"
        assert items[0].type == "blob"
        assert items[0].size == 100
        assert items[1].type == "tree"
        assert items[1].size is None

    async def test_filters_out_non_blob_and_non_tree_types(self):
        client = _make_client()
        client._client.get.return_value = _mock_response({
            "tree": [
                {"path": "file.ts", "type": "blob", "size": 10},
                {"path": "tag_ref", "type": "tag", "size": None},
                {"path": "commit_ref", "type": "commit", "size": None},
            ],
            "truncated": False,
        })

        items = await client.get_repository_tree("org", "repo")

        assert len(items) == 1
        assert items[0].path == "file.ts"

    async def test_empty_tree_returns_empty_list(self):
        client = _make_client()
        client._client.get.return_value = _mock_response({"tree": [], "truncated": False})

        items = await client.get_repository_tree("org", "repo")

        assert items == []

    async def test_branch_is_included_in_url(self):
        client = _make_client()
        client._client.get.return_value = _mock_response({"tree": [], "truncated": False})

        await client.get_repository_tree("org", "repo", branch="develop")

        call_url = client._client.get.call_args[0][0]
        assert "develop" in call_url


# ---------------------------------------------------------------------------
# get_file_content
# ---------------------------------------------------------------------------


class TestGetFileContent:
    async def test_base64_text_file_decoded(self):
        client = _make_client()
        encoded = base64.b64encode(b"hello world\n").decode()
        client._client.get.return_value = _mock_response({
            "path": "README.md",
            "content": encoded,
            "encoding": "base64",
            "sha": "abc123",
            "size": 12,
        })

        result = await client.get_file_content("org", "repo", "README.md")

        assert isinstance(result, FileContent)
        assert result.content == "hello world\n"
        assert result.path == "README.md"
        assert result.sha == "abc123"
        assert result.size == 12

    async def test_binary_file_returns_none_content(self):
        client = _make_client()
        # PNG マジックバイト（UTF-8 デコード不可）
        encoded = base64.b64encode(bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A])).decode()
        client._client.get.return_value = _mock_response({
            "path": "image.png",
            "content": encoded,
            "encoding": "base64",
            "sha": "def456",
            "size": 6,
        })

        result = await client.get_file_content("org", "repo", "image.png")

        assert result.content is None
        assert result.sha == "def456"

    async def test_no_encoding_returns_none_content(self):
        client = _make_client()
        client._client.get.return_value = _mock_response({
            "path": "file.bin",
            "content": None,
            "encoding": None,
            "sha": "ghi789",
            "size": 0,
        })

        result = await client.get_file_content("org", "repo", "file.bin")

        assert result.content is None

    async def test_ref_parameter_is_forwarded(self):
        client = _make_client()
        encoded = base64.b64encode(b"content").decode()
        client._client.get.return_value = _mock_response({
            "path": "main.py",
            "content": encoded,
            "encoding": "base64",
            "sha": "xyz",
            "size": 7,
        })

        await client.get_file_content("org", "repo", "main.py", ref="v1.0.0")

        _, kwargs = client._client.get.call_args
        assert kwargs["params"]["ref"] == "v1.0.0"
