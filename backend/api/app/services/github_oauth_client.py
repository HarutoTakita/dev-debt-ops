"""GitHub OAuth2 client with fallback when email is unavailable."""

from typing import cast

import httpx
from httpx_oauth.clients.github import GitHubOAuth2
from httpx_oauth.exceptions import GetIdEmailError


class RobustGitHubOAuth2(GitHubOAuth2):
    """GitHub OAuth2 client that falls back to the login name when email is not accessible.

    GitHub App で Email addresses 権限が未設定の場合でも動作する。
    """

    async def get_id_email(self, token: str) -> tuple[str, str | None]:
        """Return the user ID and email; continues with only the ID if email retrieval fails."""
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
                    # Do NOT fall back to an unverified address (issue-041): with
                    # associate_by_email, linking on an unverified email enables account
                    # takeover. Fall through to the synthesized noreply form instead.
            except (httpx.HTTPStatusError, GetIdEmailError):
                pass

        # 3. それでも取得できなければ {id}+{login}@users.noreply.github.com を使う
        if not email:
            email = f"{user_id}+{login}@users.noreply.github.com"

        return user_id, email
