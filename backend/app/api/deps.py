from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import get_async_session, get_sa_async_session
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.security import current_active_user, current_superuser
from app.models.org import ROLE_HIERARCHY, Org, OrgMember, OrgRole
from app.models.user import User
from app.services.github_app import GitHubAppService
from app.services.github_git_client import GitHubGitClient

SessionDep = Annotated[AsyncSession, Depends(get_async_session)]
SASessionDep = Annotated[SAAsyncSession, Depends(get_sa_async_session)]
CurrentUser = Annotated[User, Depends(current_active_user)]
CurrentSuperuser = Annotated[User, Depends(current_superuser)]


async def resolve_org_membership(
    slug: Annotated[str, Path(description="Org slug")],
    current_user: CurrentUser,
    session: SessionDep,
) -> tuple[Org, OrgMember]:
    """Resolve the `(org, membership)` pair for the current user."""
    result = await session.exec(
        select(Org, OrgMember)
        .join(OrgMember, col(OrgMember.org_id) == col(Org.id))
        .where(
            Org.slug == slug,
            col(Org.deleted_at).is_(None),
            OrgMember.user_id == current_user.id,
            col(OrgMember.deleted_at).is_(None),
        )
    )
    row = result.first()
    if not row:
        org_result = await session.exec(select(Org).where(Org.slug == slug, col(Org.deleted_at).is_(None)))
        if not org_result.first():
            raise NotFoundError("Organization not found")
        raise PermissionDeniedError("Not a member of this organization")

    org, membership = row
    return org, membership


def require_role(minimum_role: OrgRole):
    """Dependency factory that enforces a minimum org role on the caller."""

    async def check(
        org_membership: Annotated[tuple[Org, OrgMember], Depends(resolve_org_membership)],
    ) -> tuple[Org, OrgMember]:
        org, membership = org_membership
        if ROLE_HIERARCHY[membership.role] < ROLE_HIERARCHY[minimum_role]:
            raise PermissionDeniedError("Insufficient permissions")
        return org, membership

    return check


OrgScope = Annotated[tuple[Org, OrgMember], Depends(resolve_org_membership)]
OrgAdminScope = Annotated[tuple[Org, OrgMember], Depends(require_role(OrgRole.ADMIN))]
OrgOwnerScope = Annotated[tuple[Org, OrgMember], Depends(require_role(OrgRole.OWNER))]


def require_owner_or_role(resource, membership: OrgMember, minimum_role: OrgRole = OrgRole.ADMIN) -> None:
    """Allow the action if the caller owns the resource, or if their role meets `minimum_role`."""
    if resource.user_id != membership.user_id and ROLE_HIERARCHY[membership.role] < ROLE_HIERARCHY[minimum_role]:
        raise PermissionDeniedError("Insufficient permissions")


_github_app_service: GitHubAppService | None = None


def get_github_app_service() -> GitHubAppService:
    """シングルトンの GitHubAppService を返す。"""
    global _github_app_service
    if _github_app_service is None:
        _github_app_service = GitHubAppService(
            app_id=settings.GITHUB_APP_ID,
            private_key=settings.GITHUB_APP_PRIVATE_KEY.get_secret_value(),
        )
    return _github_app_service


async def get_github_git_client(
    user: CurrentUser,
) -> GitHubGitClient:
    """ログインユーザーの GitHub インストールトークンで GitHubGitClient を返す。"""
    app_service = get_github_app_service()
    # installation_id はリポジトリ選択時に取得するため、ここでは user access token を使う
    # 現時点では App JWT で直接 user installation を取得
    # TODO: ユーザー毎のインストール ID をDBに保存する方式に切り替える
    raise NotImplementedError("Use get_git_client_for_repo instead")
