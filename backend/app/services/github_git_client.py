"""GitHub REST API クライアント（インストールトークンで認証）。"""

import base64
from dataclasses import dataclass

import httpx

API_BASE = "https://api.github.com"


@dataclass
class RepositoryInfo:
    """リポジトリ基本情報。"""

    owner: str
    name: str
    full_name: str
    description: str
    url: str
    default_branch: str
    private: bool
    updated_at: str


@dataclass
class TreeItem:
    """ファイルツリーの1エントリ。"""

    path: str
    type: str  # "blob" | "tree"
    size: int | None


@dataclass
class FileContent:
    """ファイルの内容。"""

    path: str
    content: str | None
    sha: str
    size: int


class GitHubGitClient:
    """インストールアクセストークンで GitHub REST API を呼び出すクライアント。"""

    def __init__(self, access_token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def list_repositories(self, page: int = 1, per_page: int = 100) -> list[RepositoryInfo]:
        """GitHub App がインストールされているリポジトリ一覧を返す。"""
        per_page = min(per_page, 100)
        resp = await self._client.get(
            "/installation/repositories",
            params={"per_page": per_page, "page": page},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            RepositoryInfo(
                owner=r["owner"]["login"],
                name=r["name"],
                full_name=r["full_name"],
                description=r.get("description") or "",
                url=r["html_url"],
                default_branch=r.get("default_branch", "main"),
                private=r["private"],
                updated_at=r.get("pushed_at") or r.get("updated_at", ""),
            )
            for r in data.get("repositories", [])
        ]

    async def get_repository_tree(
        self, owner: str, repo: str, branch: str = "main"
    ) -> list[TreeItem]:
        """ファイルツリーを再帰的に取得する。"""
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

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str = "main"
    ) -> FileContent:
        """指定ファイルの内容を取得する。バイナリは content=None で返す。"""
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
                content = None  # バイナリファイル

        return FileContent(
            path=data["path"],
            content=content,
            sha=data["sha"],
            size=data.get("size", 0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
