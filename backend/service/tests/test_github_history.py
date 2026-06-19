"""issue 027: commit 履歴 / blame / PR レビュー取得・authorship 突合・依存抽出のテスト。

GitHubGitClient の新メソッドは underlying httpx クライアントをモックして dataclass へのマップを検証し、
authorship は ctx.session をモックして突合とフォールバックを、依存抽出は純粋関数として検証する。
方式 B（token を mint してから client を生成）は stack_analysis 側で検証済みのため、ここでは
履歴メソッド単体（token が引数で渡る前提）に集中する。
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

from service.services.authorship import AuthorIdentity, resolve_author_user_id
from service.services.dependency_extraction import DependencyEdge, extract_dependencies
from service.services.github_git_client import GitHubGitClient


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
