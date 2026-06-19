"""Authorship resolution: map a GitHub commit/blame author to a Rosetta ``users.id``.

fastapi-users' ``oauth_accounts`` table stores **no login column** — GitHub identity is the
numeric ``account_id`` (the GitHub user-node id) plus ``account_email``; the login is only
resolved at request time by calling ``/user`` with the stored token
(``api/app/api/v1/github.py`` ``resolve_installation_id``). Offline analysis (commit/blame)
therefore keys on ``account_id`` first (stable and unambiguous — it is exactly what the REST
``author.id`` / GraphQL ``databaseId`` fields provide) and falls back to ``account_email``.

When no Rosetta user is linked (external committer), the caller gets ``None`` and is expected
to keep the raw GitHub handle — see ADR ``docs/adr/0002-git-history-access-and-authorship.md``.

The lookup runs against the api-owned ``oauth_accounts`` table via raw SQL on the pipeline's
``ctx.session`` because the service container cannot import the ``app.*`` ORM models.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_BY_ACCOUNT_ID = text(
    "SELECT user_id FROM oauth_accounts WHERE oauth_name = 'github' AND account_id = :account_id LIMIT 1"
)
_BY_EMAIL = text(
    "SELECT user_id FROM oauth_accounts WHERE oauth_name = 'github' AND lower(account_email) = lower(:email) LIMIT 1"
)


@dataclass(frozen=True)
class AuthorIdentity:
    """A GitHub author as seen from a commit/blame range.

    ``github_user_id`` is the GitHub user-node id (REST ``author.id`` / GraphQL ``databaseId``);
    ``login`` is carried for logging/handle-preservation but is **not** a match key because it is
    not persisted by fastapi-users.
    """

    login: str | None = None
    email: str | None = None
    github_user_id: int | None = None


def _as_uuid(value: object) -> uuid.UUID | None:
    """Coerce a DB ``user_id`` cell (``uuid.UUID`` or ``str``) into a ``UUID``."""
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        return uuid.UUID(value)
    return None


async def resolve_author_user_id(session: AsyncSession, identity: AuthorIdentity) -> uuid.UUID | None:
    """Return the Rosetta ``users.id`` linked to ``identity``, or ``None`` if unlinked.

    Matches on the GitHub ``account_id`` first (precise), then ``account_email`` (case-insensitive)
    as a fallback. ``None`` means no linked Rosetta user — keep the raw GitHub handle.
    """
    if identity.github_user_id is not None:
        row = (await session.execute(_BY_ACCOUNT_ID, {"account_id": str(identity.github_user_id)})).first()
        if row is not None:
            return _as_uuid(row[0])

    if identity.email:
        row = (await session.execute(_BY_EMAIL, {"email": identity.email})).first()
        if row is not None:
            return _as_uuid(row[0])

    return None
