"""issue 027: commit 履歴 / blame / PR レビュー取得・authorship 突合・依存抽出のテスト。

GitHubGitClient の新メソッドは underlying httpx クライアントをモックして dataclass へのマップを検証し、
authorship は ctx.session をモックして突合とフォールバックを、依存抽出は純粋関数として検証する。
方式 B（token を mint してから client を生成）は stack_analysis 側で検証済みのため、ここでは
履歴メソッド単体（token が引数で渡る前提）に集中する。
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from service.services.authorship import AuthorIdentity, resolve_author_user_id
from service.services.dependency_extraction import DependencyEdge, extract_dependencies
from service.services.github_git_client import (
    _MAX_RETRIES,
    CachingGitHubGitClient,
    GitHubGitClient,
    LocalCloneGitHubClient,
    _InstallationTokenAuth,
    _RetryTransport,
)


def _client_with_response(json_data: object, *, method: str = "get") -> GitHubGitClient:
    """Return a GitHubGitClient whose underlying httpx call returns ``json_data``."""
    response = MagicMock()
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    client = GitHubGitClient(access_token="t")
    client._client = AsyncMock()
    getattr(client._client, method).return_value = response
    return client


class TestListCommits:
    async def test_maps_git_and_github_author(self) -> None:
        client = _client_with_response(
            [
                {
                    "sha": "abc",
                    "commit": {"author": {"email": "a@x.com", "date": "2026-01-01T00:00:00Z"}, "message": "msg"},
                    "author": {"login": "alice", "id": 42},
                },
                {
                    "sha": "def",
                    "commit": {"author": {"email": "b@x.com", "date": "2026-01-02T00:00:00Z"}, "message": "m2"},
                    "author": None,
                },
            ]
        )
        commits = await client.list_commits("o", "r", path="src/a.py")
        assert commits[0].sha == "abc"
        assert commits[0].author_login == "alice"
        assert commits[0].author_id == 42
        assert commits[0].author_email == "a@x.com"
        # author が GitHub ユーザに紐づかない commit は login/id が None、email は git author 由来で残る。
        assert commits[1].author_login is None
        assert commits[1].author_id is None
        assert commits[1].author_email == "b@x.com"


class TestGetBlame:
    async def test_parses_graphql_ranges(self) -> None:
        client = _client_with_response(
            {
                "data": {
                    "repository": {
                        "object": {
                            "blame": {
                                "ranges": [
                                    {
                                        "startingLine": 1,
                                        "endingLine": 10,
                                        "commit": {
                                            "oid": "sha1",
                                            "author": {
                                                "email": "a@x.com",
                                                "user": {"login": "alice", "databaseId": 42},
                                            },
                                        },
                                    },
                                    {
                                        "startingLine": 11,
                                        "endingLine": 12,
                                        "commit": {"oid": "sha2", "author": {"email": "ext@x.com", "user": None}},
                                    },
                                ]
                            }
                        }
                    }
                }
            },
            method="post",
        )
        ranges = await client.get_blame("o", "r", "src/a.py")
        assert ranges[0].start_line == 1
        assert ranges[0].end_line == 10
        assert ranges[0].commit_sha == "sha1"
        assert ranges[0].author_login == "alice"
        assert ranges[0].author_id == 42
        # 外部コミッタ（GitHub ユーザ未リンク）は login/id None・email は残す。
        assert ranges[1].author_login is None
        assert ranges[1].author_id is None
        assert ranges[1].commit_sha == "sha2"

    async def test_missing_object_returns_empty(self) -> None:
        client = _client_with_response({"data": {"repository": {"object": None}}}, method="post")
        assert await client.get_blame("o", "r", "missing.py") == []


class TestPullRequests:
    async def test_list_pull_requests(self) -> None:
        client = _client_with_response(
            [
                {"number": 1, "merged_at": "2026-01-01T00:00:00Z", "merged_by": {"login": "bob"}},
                {"number": 2, "merged_at": None, "merged_by": None},
            ]
        )
        pulls = await client.list_pull_requests("o", "r")
        assert pulls[0].number == 1
        assert pulls[0].merged_by_login == "bob"
        assert pulls[1].merged_at is None
        assert pulls[1].merged_by_login is None

    async def test_get_reviews(self) -> None:
        client = _client_with_response(
            [
                {"state": "APPROVED", "user": {"login": "carol"}, "submitted_at": "t"},
                {"state": "COMMENTED", "user": None, "submitted_at": None},
            ]
        )
        reviews = await client.get_pull_request_reviews("o", "r", 1)
        assert reviews[0].state == "APPROVED"
        assert reviews[0].author_login == "carol"
        assert reviews[1].author_login is None


def _session_returning(*first_results: object) -> AsyncMock:
    """Mock AsyncSession whose successive ``execute(...).first()`` return the given values."""
    results = []
    for value in first_results:
        result = MagicMock()
        result.first.return_value = value
        results.append(result)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=results)
    return session


class TestAuthorship:
    async def test_resolves_by_account_id(self) -> None:
        uid = uuid.uuid4()
        session = _session_returning((uid,))
        resolved = await resolve_author_user_id(session, AuthorIdentity(login="alice", github_user_id=42))
        assert resolved == uid
        # account_id 一致で確定したら email クエリは走らない。
        assert session.execute.await_count == 1

    async def test_falls_back_to_email(self) -> None:
        uid = uuid.uuid4()
        # 1 回目（account_id）None → 2 回目（email）ヒット。
        session = _session_returning(None, (str(uid),))
        resolved = await resolve_author_user_id(session, AuthorIdentity(email="a@x.com", github_user_id=99))
        assert resolved == uid
        assert session.execute.await_count == 2

    async def test_returns_none_when_unlinked(self) -> None:
        session = _session_returning(None, None)
        resolved = await resolve_author_user_id(
            session, AuthorIdentity(login="ext", email="ext@x.com", github_user_id=7)
        )
        assert resolved is None

    async def test_no_identity_no_query(self) -> None:
        session = _session_returning()
        assert await resolve_author_user_id(session, AuthorIdentity(login="onlylogin")) is None
        assert session.execute.await_count == 0


class TestDependencyExtraction:
    def test_python_relative_and_absolute(self) -> None:
        repo = {"pkg/mod.py", "pkg/sibling.py", "pkg/sub.py", "app/util.py"}
        content = (
            "from . import sibling\n"
            "from .sub import thing\n"
            "import app.util\n"
            "import os\n"  # 標準ライブラリ → 除外
            "from third_party import x\n"  # 外部 → 除外
        )
        edges = set(extract_dependencies("pkg/mod.py", content, repo))
        assert DependencyEdge("pkg/mod.py", "pkg/sibling.py") in edges
        assert DependencyEdge("pkg/mod.py", "pkg/sub.py") in edges
        assert DependencyEdge("pkg/mod.py", "app/util.py") in edges
        # 外部パッケージ・標準ライブラリのエッジは無い。
        assert all(e.to_path in repo for e in edges)
        assert len(edges) == 3

    def test_ts_relative_only(self) -> None:
        repo = {"src/a.ts", "src/b.ts", "src/c/index.ts"}
        content = (
            'import { b } from "./b";\n'
            'import c from "./c";\n'  # ディレクトリ → ./c/index.ts
            'import React from "react";\n'  # bare → 除外
            'const x = require("../outside");\n'  # 解決不能 → 除外
        )
        edges = set(extract_dependencies("src/a.ts", content, repo))
        assert DependencyEdge("src/a.ts", "src/b.ts") in edges
        assert DependencyEdge("src/a.ts", "src/c/index.ts") in edges
        assert len(edges) == 2

    def test_self_edge_and_unknown_language_excluded(self) -> None:
        # 自己参照は除外。
        assert extract_dependencies("a.py", "import a\n", {"a.py"}) == []
        # 未対応言語（拡張子）は空。
        assert extract_dependencies("README.md", "import x from './y'", {"y.md"}) == []


class TestGetRepositoryTree:
    async def test_truncated_logs_warning(self, caplog: object) -> None:
        """078-E: a truncated tree still returns its (partial) items and surfaces a warning."""
        client = _client_with_response({"tree": [{"path": "a.py", "type": "blob", "size": 10}], "truncated": True})
        with caplog.at_level("WARNING"):
            items = await client.get_repository_tree("o", "r", "main")
        assert [i.path for i in items] == ["a.py"]
        assert any("truncated" in rec.message for rec in caplog.records)


class TestGetFileContent:
    async def test_recovers_non_utf8_text(self) -> None:
        """078-F: non-UTF-8 text (latin-1) is recovered leniently, not dropped to None."""
        import base64 as b64

        raw = "café".encode("latin-1")  # 0xE9 is invalid UTF-8
        client = _client_with_response(
            {"path": "a.py", "sha": "s", "size": len(raw), "encoding": "base64", "content": b64.b64encode(raw).decode()}
        )
        fc = await client.get_file_content("o", "r", "a.py")
        assert fc.content is not None

    async def test_binary_returns_none(self) -> None:
        """078-F: content with NUL bytes is treated as binary → None."""
        import base64 as b64

        raw = b"\x00\x01\x02binary"
        client = _client_with_response(
            {
                "path": "a.bin",
                "sha": "s",
                "size": len(raw),
                "encoding": "base64",
                "content": b64.b64encode(raw).decode(),
            }
        )
        fc = await client.get_file_content("o", "r", "a.bin")
        assert fc.content is None

    async def test_oversize_fetched_via_raw(self) -> None:
        """078-F: a >1MB file (Contents API encoding='none') is fetched via the raw media type."""
        contents_resp = MagicMock()
        contents_resp.json.return_value = {
            "path": "big.py",
            "sha": "s",
            "size": 2_000_000,
            "type": "file",
            "encoding": "none",
            "content": "",
        }
        contents_resp.raise_for_status = MagicMock()
        raw_resp = MagicMock()
        raw_resp.content = b"x = 1\n" * 100
        raw_resp.raise_for_status = MagicMock()
        client = GitHubGitClient(access_token="t")
        client._client = AsyncMock()
        client._client.get.side_effect = [contents_resp, raw_resp]  # 1) contents (not inlined) 2) raw bytes
        fc = await client.get_file_content("o", "r", "big.py")
        assert fc.content is not None
        assert "x = 1" in fc.content


class TestInstallationTokenRefresh:
    async def test_auth_refreshes_on_401_and_replays(self) -> None:
        """078-D: a 401 re-mints the token and replays the request once with the fresh Bearer header."""
        calls = {"n": 0}

        async def provider() -> str:
            calls["n"] += 1
            return "fresh-token"

        auth = _InstallationTokenAuth("stale-token", provider)
        request = httpx.Request("GET", "https://api.github.com/x")
        flow = auth.async_auth_flow(request)
        req1 = await flow.__anext__()
        assert req1.headers["Authorization"] == "Bearer stale-token"
        req2 = await flow.asend(httpx.Response(401, request=request))  # 401 → refresh + replay
        assert req2.headers["Authorization"] == "Bearer fresh-token"
        assert calls["n"] == 1
        with pytest.raises(StopAsyncIteration):
            await flow.asend(httpx.Response(200, request=request))

    async def test_auth_no_refresh_on_success(self) -> None:
        """078-D: a non-401 response ends the flow without re-minting."""
        calls = {"n": 0}

        async def provider() -> str:
            calls["n"] += 1
            return "x"

        auth = _InstallationTokenAuth("t", provider)
        request = httpx.Request("GET", "https://api.github.com/x")
        flow = auth.async_auth_flow(request)
        await flow.__anext__()
        with pytest.raises(StopAsyncIteration):
            await flow.asend(httpx.Response(200, request=request))
        assert calls["n"] == 0  # provider not called on success

    def test_client_token_provider_installs_refresh_auth(self) -> None:
        """078-D: a token_provider installs the refresh auth; without one, the static header is kept."""

        async def provider() -> str:
            return "t"

        client = GitHubGitClient(access_token="init", token_provider=provider)
        assert isinstance(client._client.auth, _InstallationTokenAuth)
        assert "authorization" not in {k.lower() for k in client._client.headers}
        plain = GitHubGitClient(access_token="init")  # no provider → static header (unchanged behaviour)
        assert plain._client.headers.get("Authorization") == "Bearer init"


class _FakeInner:
    """Stub inner transport returning a scripted sequence of status codes (last one repeats)."""

    def __init__(self, statuses: list[int]) -> None:
        self._statuses = statuses
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        code = self._statuses[min(self.calls, len(self._statuses) - 1)]
        self.calls += 1
        return httpx.Response(code, request=request)

    async def aclose(self) -> None:
        return None


class TestRetryTransport:
    async def test_retries_transient_5xx_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A transient 502 GET is retried and succeeds (the analysis-step failure this fixes)."""
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        t = _RetryTransport()
        t._inner = _FakeInner([502, 200])
        resp = await t.handle_async_request(httpx.Request("GET", "https://api.github.com/x"))
        assert resp.status_code == 200
        assert t._inner.calls == 2

    async def test_gives_up_after_max_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        t = _RetryTransport()
        t._inner = _FakeInner([503])
        resp = await t.handle_async_request(httpx.Request("GET", "https://api.github.com/x"))
        assert resp.status_code == 503
        assert t._inner.calls == 1 + _MAX_RETRIES  # initial attempt + retries

    async def test_does_not_retry_non_get(self) -> None:
        """Mutations (POST/PATCH) are not replayed — no double-create."""
        t = _RetryTransport()
        t._inner = _FakeInner([502])
        resp = await t.handle_async_request(httpx.Request("POST", "https://api.github.com/x"))
        assert resp.status_code == 502
        assert t._inner.calls == 1


class TestLocalCloneGitHubClient:
    """Reads tree/file content from a local clone instead of the Contents API (removes the 502 source)."""

    def _make(self, tmp_path) -> LocalCloneGitHubClient:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("print('a')\n", encoding="utf-8")
        (tmp_path / "readme.md").write_text("# hi\n", encoding="utf-8")
        (tmp_path / "bin.dat").write_bytes(b"\x00\x01\x02binary")
        git = tmp_path / ".git"
        git.mkdir()
        (git / "config").write_text("[core]\n", encoding="utf-8")  # must be pruned from the tree
        return LocalCloneGitHubClient(str(tmp_path), access_token="t")

    async def test_tree_lists_files_as_sorted_blobs_and_prunes_git(self, tmp_path) -> None:
        client = self._make(tmp_path)
        tree = await client.get_repository_tree("o", "r", "main")
        paths = [t.path for t in tree]
        assert paths == ["bin.dat", "readme.md", "src/a.py"]  # path-sorted, .git excluded
        assert all(t.type == "blob" for t in tree)

    async def test_file_content_reads_from_disk(self, tmp_path) -> None:
        client = self._make(tmp_path)
        fc = await client.get_file_content("o", "r", "src/a.py", "main")
        assert fc.content == "print('a')\n"

    async def test_binary_file_returns_none(self, tmp_path) -> None:
        client = self._make(tmp_path)
        fc = await client.get_file_content("o", "r", "bin.dat", "main")
        assert fc.content is None  # NUL byte → treated as binary

    async def test_missing_and_traversal_return_none(self, tmp_path) -> None:
        client = self._make(tmp_path)
        assert (await client.get_file_content("o", "r", "nope.py", "main")).content is None
        assert (await client.get_file_content("o", "r", "../../etc/passwd", "main")).content is None

    def test_delegates_history_methods_by_inheritance(self, tmp_path) -> None:
        """blame / list_commits / PR reviews are inherited (API) — only tree/file are local."""
        client = self._make(tmp_path)
        assert isinstance(client, CachingGitHubGitClient)  # inherits the API read/history methods
        assert type(client).get_blame is GitHubGitClient.get_blame  # blame not overridden → hits the API
