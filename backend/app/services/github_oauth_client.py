"""GitHub OAuth2 クライアント（メール未取得時のフォールバック付き）。"""

from typing import cast

import httpx
from httpx_oauth.clients.github import GitHubOAuth2
from httpx_oauth.exceptions import GetIdEmailError


class RobustGitHubOAuth2(GitHubOAuth2):
    """メールが取得できない場合に GitHub ログイン名をフォールバックとして使うクライアント。

    GitHub App で Email addresses 権限が未設定の場合でも動作する。
    """

    async def get_id_email(self, token: str) -> tuple[str, str | None]:
        """ユーザー ID とメールアドレスを返す。メール取得に失敗しても ID だけで続行する。"""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        user_id = str(data["id"])
        login = cast(str, data.get("login", ""))

        # 1. /user レスポンスにメールが含まれていればそれを使う
        email: str | None = data.get("email") or None

        if not email:
            # 2. /user/emails を試みる
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://api.github.com/user/emails",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28",
                        },
                    )
                    resp.raise_for_status()
                    emails = resp.json()
                    for entry in emails:
                        if entry.get("primary") and entry.get("verified"):
                            email = entry["email"]
                            break
                    if not email and emails:
                        email = emails[0].get("email")
            except (httpx.HTTPStatusError, GetIdEmailError):
                pass

        # 3. それでも取得できなければ {id}+{login}@users.noreply.github.com を使う
        if not email:
            email = f"{user_id}+{login}@users.noreply.github.com"

        return user_id, email
