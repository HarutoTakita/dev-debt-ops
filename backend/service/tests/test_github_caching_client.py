"""CachingGitHubGitClient — per-job read memoisation (取得の共通化)."""

import pytest

from service.services import github_git_client as ggc
from service.services.github_git_client import CachingGitHubGitClient


async def test_caches_tree_and_files_and_keys_by_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated identical reads hit the underlying client once; different args fetch separately."""
    tree_calls = {"n": 0}
    file_calls = {"n": 0}

    async def fake_tree(self: object, owner: str, repo: str, branch: str = "main") -> list[object]:
        tree_calls["n"] += 1
        return [{"branch": branch}]

    async def fake_file(self: object, owner: str, repo: str, path: str, ref: str = "main") -> dict[str, str]:
        file_calls["n"] += 1
        return {"path": path}

    monkeypatch.setattr(ggc.GitHubGitClient, "get_repository_tree", fake_tree)
    monkeypatch.setattr(ggc.GitHubGitClient, "get_file_content", fake_file)

    client = CachingGitHubGitClient(access_token="t")
    try:
        t1 = await client.get_repository_tree("o", "r", "main")
        t2 = await client.get_repository_tree("o", "r", "main")
        assert t1 is t2  # same cached object returned
        assert tree_calls["n"] == 1  # underlying fetch happened once
        await client.get_repository_tree("o", "r", "dev")  # different branch → separate fetch
        assert tree_calls["n"] == 2

        f1 = await client.get_file_content("o", "r", "a.py", "main")
        f2 = await client.get_file_content("o", "r", "a.py", "main")
        assert f1 is f2
        assert file_calls["n"] == 1
        await client.get_file_content("o", "r", "b.py", "main")  # different path → separate fetch
        assert file_calls["n"] == 2
    finally:
        await client.aclose()
