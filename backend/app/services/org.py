import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_async_session
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models.org import Org, OrgMember, OrgRole
from app.models.user import User
from app.schemas.org import OrgCreate, OrgUpdate


class OrgService:
    """Business logic for orgs and memberships.

    Route handlers stay thin: they validate input, call a service method, and
    shape the response. Domain rules (e.g. "cannot leave personal org", "last
    owner cannot leave") live here so they're testable without an HTTP client
    and reusable across different routes or background jobs.
    """

    def __init__(self, session: Annotated[AsyncSession, Depends(get_async_session)]) -> None:
        self.session = session

    async def list_for_user(self, user: User) -> list[Org]:
        """Return every active org the user is an active member of."""
        result = await self.session.exec(
            select(Org)
            .join(OrgMember, col(OrgMember.org_id) == col(Org.id))
            .where(
                OrgMember.user_id == user.id,
                col(OrgMember.deleted_at).is_(None),
                col(Org.deleted_at).is_(None),
            )
        )
        return list(result.all())

    async def create(self, body: OrgCreate, user: User) -> Org:
        """Create a new org with the caller as its first owner.

        Raises:
            ConflictError: If the slug is already in use.
        """
        org = Org(name=body.name, slug=body.slug, is_personal=False, created_by=user.id)
        self.session.add(org)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError("Slug already in use") from None

        member = OrgMember(user_id=user.id, org_id=org.id, role=OrgRole.OWNER)
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(org)
        return org

    async def update(self, org: Org, body: OrgUpdate) -> Org:
        """Patch mutable fields on an existing org. Currently only `name`."""
        if body.name is not None:
            org.name = body.name
        self.session.add(org)
        await self.session.commit()
        await self.session.refresh(org)
        return org

    async def delete(self, org: Org) -> None:
        """Soft-delete an org and all of its memberships.

        Raises:
            PermissionDeniedError: If the org is a personal org (cannot be deleted).
        """
        if org.is_personal:
            raise PermissionDeniedError("Cannot delete personal organization")

        now = datetime.now(UTC)
        org.deleted_at = now
        self.session.add(org)

        await self.session.exec(
            update(OrgMember)
            .where(col(OrgMember.org_id) == org.id, col(OrgMember.deleted_at).is_(None))
            .values(deleted_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )

        await self.session.commit()

    async def leave(self, org: Org, membership: OrgMember) -> None:
        """Soft-delete the caller's membership.

        Raises:
            PermissionDeniedError: If org is personal, or if caller is the last owner.
        """
        if org.is_personal:
            raise PermissionDeniedError("Cannot leave personal organization")

        if membership.role == OrgRole.OWNER:
            result = await self.session.exec(
                select(OrgMember).where(
                    OrgMember.org_id == org.id,
                    OrgMember.role == OrgRole.OWNER,
                    col(OrgMember.deleted_at).is_(None),
                )
            )
            owners = result.all()
            if len(owners) <= 1:
                raise PermissionDeniedError("Cannot leave: you are the last owner")

        membership.deleted_at = datetime.now(UTC)
        self.session.add(membership)
        await self.session.commit()

    async def list_members(self, org: Org) -> list[tuple[OrgMember, User]]:
        """Return all active memberships with their associated user rows, for the given org."""
        result = await self.session.exec(
            select(OrgMember, User)
            .join(User, col(OrgMember.user_id) == col(User.id))
            .where(
                OrgMember.org_id == org.id,
                col(OrgMember.deleted_at).is_(None),
                col(User.deleted_at).is_(None),
            )
        )
        return list(result.all())

    async def invite(self, org: Org, email: str) -> tuple[OrgMember, User]:
        """Invite an existing user to the org as a MEMBER.

        Raises:
            PermissionDeniedError: If the org is personal.
            NotFoundError: If no user exists with the given email.
            ConflictError: If the user is already a member.
        """
        if org.is_personal:
            raise PermissionDeniedError("Cannot invite members to personal organization")

        result = await self.session.exec(select(User).where(User.email == email))
        user = result.first()
        if not user:
            raise NotFoundError("User not found")

        result = await self.session.exec(
            select(OrgMember).where(
                OrgMember.org_id == org.id,
                OrgMember.user_id == user.id,
                col(OrgMember.deleted_at).is_(None),
            )
        )
        if result.first():
            raise ConflictError("User is already a member")

        member = OrgMember(user_id=user.id, org_id=org.id, role=OrgRole.MEMBER)
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(member)
        return member, user

    async def remove_member(self, org: Org, user_id: uuid.UUID) -> None:
        """Remove a member from the org.

        Owners cannot be removed via this method; they must transfer ownership first.

        Raises:
            NotFoundError: If no active membership exists for that user in the org.
            PermissionDeniedError: If the target member is an owner.
        """
        result = await self.session.exec(
            select(OrgMember).where(
                OrgMember.org_id == org.id,
                OrgMember.user_id == user_id,
                col(OrgMember.deleted_at).is_(None),
            )
        )
        target = result.first()
        if not target:
            raise NotFoundError("Member not found")

        if target.role == OrgRole.OWNER:
            raise PermissionDeniedError("Cannot remove an owner")

        target.deleted_at = datetime.now(UTC)
        self.session.add(target)
        await self.session.commit()

    async def change_member_role(self, org: Org, user_id: uuid.UUID, role: OrgRole) -> tuple[OrgMember, User]:
        """Change a member's role within the org.

        Returns:
            Updated membership row paired with the user record.

        Raises:
            NotFoundError: If no active membership exists for that user in the org.
        """
        result = await self.session.exec(
            select(OrgMember, User)
            .join(User, col(OrgMember.user_id) == col(User.id))
            .where(
                OrgMember.org_id == org.id,
                OrgMember.user_id == user_id,
                col(OrgMember.deleted_at).is_(None),
            )
        )
        row = result.first()
        if not row:
            raise NotFoundError("Member not found")

        target, user = row
        target.role = role
        self.session.add(target)
        await self.session.commit()
        await self.session.refresh(target)
        return target, user


OrgServiceDep = Annotated[OrgService, Depends(OrgService)]
