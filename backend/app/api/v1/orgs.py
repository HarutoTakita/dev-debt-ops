import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.api.deps import CurrentUser, OrgAdminScope, OrgOwnerScope, OrgScope
from app.models.org import Org, OrgMember
from app.models.user import User
from app.schemas.org import (
    OrgCreate,
    OrgMemberInvite,
    OrgMemberRead,
    OrgMemberRoleUpdate,
    OrgMemberUser,
    OrgRead,
    OrgUpdate,
)
from app.services.org import OrgServiceDep

router = APIRouter(tags=["orgs"])


def _member_with_user(member: OrgMember, user: User) -> OrgMemberRead:
    """Compose an `OrgMemberRead` response from its `OrgMember` + `User` rows."""
    return OrgMemberRead(
        id=member.id,
        user_id=member.user_id,
        org_id=member.org_id,
        role=member.role,
        created_at=member.created_at,
        user=OrgMemberUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            last_active_at=user.last_active_at,
            is_active=user.is_active,
        ),
    )


# --- No org scope ---


@router.get(
    "/orgs",
    response_model=list[OrgRead],
    summary="List my orgs",
    response_description="Every active org the caller is an active member of.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
    },
)
async def list_my_orgs(current_user: CurrentUser, service: OrgServiceDep) -> list[Org]:
    """Return all orgs the caller belongs to.

    Only orgs where the caller holds an active (non-soft-deleted) membership are included.
    Soft-deleted orgs and soft-deleted memberships are filtered out.
    """
    return await service.list_for_user(current_user)


@router.post(
    "/orgs",
    response_model=OrgRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization",
    response_description="The newly created org, with the caller as its first owner.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_409_CONFLICT: {"description": "Slug already in use."},
    },
)
async def create_org(body: OrgCreate, current_user: CurrentUser, service: OrgServiceDep) -> Org:
    """Create a new organization owned by the caller.

    The caller is automatically added as the first `OWNER` member of the new org.
    Slug uniqueness is enforced among non-deleted orgs via the `uq_orgs_slug_active`
    partial unique index.

    Raises:
        ConflictError: If the slug is already in use by a non-deleted org.
    """
    return await service.create(body, current_user)


# --- Org-scoped (any member) ---


@router.get(
    "/orgs/{slug}",
    response_model=OrgRead,
    summary="Get an organization",
    response_description="Org metadata.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not a member of this org."},
        status.HTTP_404_NOT_FOUND: {"description": "Org not found."},
    },
)
async def get_org(org_membership: OrgScope) -> Org:
    """Return the org row for the given slug.

    Raises:
        NotFoundError: If no active org with the given slug exists.
        PermissionDeniedError: If the caller is not an active member.
    """
    org, _ = org_membership
    return org


@router.get(
    "/orgs/{slug}/members",
    response_model=list[OrgMemberRead],
    summary="List org members",
    response_description="Every active member of the org, each nested with a user summary.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not a member of this org."},
        status.HTTP_404_NOT_FOUND: {"description": "Org not found."},
    },
)
async def list_members(org_membership: OrgScope, service: OrgServiceDep) -> list[OrgMemberRead]:
    """Return all active memberships for the org, each nested with the user's display data.

    Raises:
        NotFoundError: If no active org with the given slug exists.
        PermissionDeniedError: If the caller is not an active member.
    """
    org, _ = org_membership
    rows = await service.list_members(org)
    return [_member_with_user(m, u) for m, u in rows]


# --- Org-scoped (self) ---


@router.get(
    "/orgs/{slug}/me",
    response_model=OrgMemberRead,
    summary="Get my membership in this org",
    response_description="Caller's own membership record, nested with their user summary.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not a member of this org."},
        status.HTTP_404_NOT_FOUND: {"description": "Org not found."},
    },
)
async def get_my_membership(org_membership: OrgScope, current_user: CurrentUser) -> OrgMemberRead:
    """Return the caller's own membership row in this org.

    Raises:
        NotFoundError: If no active org with the given slug exists.
        PermissionDeniedError: If the caller is not an active member.
    """
    _, membership = org_membership
    return _member_with_user(membership, current_user)


@router.delete(
    "/orgs/{slug}/members/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Leave an organization",
    response_description="Caller's membership in this org is soft-deleted.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not a member, org is personal, or caller is the last owner."},
        status.HTTP_404_NOT_FOUND: {"description": "Org not found."},
    },
)
async def leave_org(org_membership: OrgScope, service: OrgServiceDep) -> None:
    """Remove the caller from the org by soft-deleting their membership.

    The request is refused if the org is a personal org, or if the caller is
    the last owner — in that case, transfer ownership to another member first.

    Raises:
        NotFoundError: If no active org with the given slug exists.
        PermissionDeniedError: If caller is not a member, the org is personal,
            or the caller is the last owner.
    """
    org, membership = org_membership
    await service.leave(org, membership)


# --- Org-scoped (admin or owner) ---


@router.patch(
    "/orgs/{slug}",
    response_model=OrgRead,
    summary="Update org metadata",
    response_description="Updated org record.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not an admin of this org."},
        status.HTTP_404_NOT_FOUND: {"description": "Org not found."},
    },
)
async def update_org(body: OrgUpdate, org_membership: OrgAdminScope, service: OrgServiceDep) -> Org:
    """Patch mutable fields on the org. Currently only the `name` field is mutable (see `OrgUpdate`).

    Raises:
        NotFoundError: If no active org with the given slug exists.
        PermissionDeniedError: If the caller is not an admin of this org.
    """
    org, _ = org_membership
    return await service.update(org, body)


@router.post(
    "/orgs/{slug}/members",
    response_model=OrgMemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user to the org",
    response_description="The newly created MEMBER record, nested with the user's summary.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not an admin, or org is personal."},
        status.HTTP_404_NOT_FOUND: {"description": "Org or invited user not found."},
        status.HTTP_409_CONFLICT: {"description": "User is already an active member."},
    },
)
async def invite_member(
    body: OrgMemberInvite,
    org_membership: OrgAdminScope,
    service: OrgServiceDep,
) -> OrgMemberRead:
    """Look up a user by email and add them to the org with MEMBER role.

    Personal orgs cannot invite additional members.

    Raises:
        NotFoundError: If no user exists with the given email, or the org is not found.
        PermissionDeniedError: If the caller is not an admin, or the org is personal.
        ConflictError: If the user is already an active member of the org.
    """
    org, _ = org_membership
    member, user = await service.invite(org, body.email)
    return _member_with_user(member, user)


@router.delete(
    "/orgs/{slug}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from the org",
    response_description="Target member's membership is soft-deleted.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not an admin, or target member is an owner."},
        status.HTTP_404_NOT_FOUND: {"description": "Org or target membership not found."},
    },
)
async def remove_member(
    user_id: Annotated[uuid.UUID, Path(description="UUID of the user to remove from the org.")],
    org_membership: OrgAdminScope,
    service: OrgServiceDep,
) -> None:
    """Soft-delete the target member's membership in the org.

    Owners cannot be removed via this endpoint — the owner must transfer ownership first.

    Raises:
        NotFoundError: If the org or target membership is not found.
        PermissionDeniedError: If the caller is not an admin, or the target member is an owner.
    """
    org, _ = org_membership
    await service.remove_member(org, user_id)


# --- Org-scoped (owner only) ---


@router.patch(
    "/orgs/{slug}/members/{user_id}",
    response_model=OrgMemberRead,
    summary="Change a member's role",
    response_description="Updated membership record, nested with the user summary.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not an owner of this org."},
        status.HTTP_404_NOT_FOUND: {"description": "Org or target membership not found."},
    },
)
async def change_member_role(
    user_id: Annotated[uuid.UUID, Path(description="UUID of the member whose role to reassign.")],
    body: OrgMemberRoleUpdate,
    org_membership: OrgOwnerScope,
    service: OrgServiceDep,
) -> OrgMemberRead:
    """Reassign an existing member's role within the org. Owner-only operation.

    Raises:
        NotFoundError: If the org or target membership is not found.
        PermissionDeniedError: If the caller is not an owner.
    """
    org, _ = org_membership
    target, user = await service.change_member_role(org, user_id, body.role)
    return _member_with_user(target, user)


@router.delete(
    "/orgs/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an organization",
    response_description="Org and all of its memberships are soft-deleted.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Not authenticated."},
        status.HTTP_403_FORBIDDEN: {"description": "Not an owner, or org is personal."},
        status.HTTP_404_NOT_FOUND: {"description": "Org not found."},
    },
)
async def delete_org(org_membership: OrgOwnerScope, service: OrgServiceDep) -> None:
    """Soft-delete the org and cascade to all of its member rows.

    Personal orgs cannot be deleted.

    Raises:
        NotFoundError: If no active org with the given slug exists.
        PermissionDeniedError: If the caller is not an owner, or the org is personal.
    """
    org, _ = org_membership
    await service.delete(org)
