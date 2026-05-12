"""GitHub App authentication: JWT signing and installation token management."""

import time
from datetime import datetime

import httpx
import jwt

API_BASE = "https://api.github.com"
_EXPIRY_BUFFER_SECONDS = 300  # 期限5分前に再取得


def _to_pem(key: str) -> str:
    """Ensure the key is in PEM format (add headers if missing)."""
    key = key.strip().replace("\\n", "\n")
    if key.startswith("-----"):
        return key
    return f"-----BEGIN RSA PRIVATE KEY-----\n{key}\n-----END RSA PRIVATE KEY-----"


class GitHubAppService:
    """GitHub App の JWT 署名とインストールアクセストークン管理。"""

    def __init__(self, app_id: str, private_key: str) -> None:
        self._app_id = app_id
        self._private_key = _to_pem(private_key)
        self._token_cache: dict[int, tuple[str, float]] = {}

    def _create_jwt(self) -> str:
        """RS256 で署名した JWT を生成（10分有効）。"""
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 600,
            "iss": self._app_id,
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    def _get_cached_token(self, installation_id: int) -> str | None:
        entry = self._token_cache.get(installation_id)
        if entry is None:
            return None
        token, expiry = entry
        if time.time() >= expiry - _EXPIRY_BUFFER_SECONDS:
            return None
        return token

    async def get_installation_token(self, installation_id: int) -> str:
        """インストールアクセストークンを取得（キャッシュあり）。"""
        cached = self._get_cached_token(installation_id)
        if cached:
            return cached

        app_jwt = self._create_jwt()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{API_BASE}/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        token = data["token"]
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
        self._token_cache[installation_id] = (token, expires_at)
        return token

    async def get_installation_for_repo(self, owner: str, repo: str) -> int:
        """リポジトリに対応するインストール ID を取得。"""
        app_jwt = self._create_jwt()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{API_BASE}/repos/{owner}/{repo}/installation",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
            return resp.json()["id"]
