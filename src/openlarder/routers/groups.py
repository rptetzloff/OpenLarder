"""Household groups: make one, invite people into it, set their roles, and
leave (migration 0027; visibility.py for what members see).

Everything about a group is seen only by its members. An admin of a group
renames or deletes it, invites people, and changes or removes members; any
member can leave. A group always keeps an admin: the last one can't leave,
be removed or step down, short of deleting the group.

An invite is for one person: a link that works once and expires after
INVITE_DAYS (Ray, 2026-11-08). Its token is shown once, when it's made; only
its hash is kept. Opening the link says which group and role it's for, and
accepting it needs an account.

When someone leaves a group, or is removed, their collections stop being
shared with it.
"""

import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update

from openlarder.auth import CurrentUser, SameOrigin, hash_token, new_token
from openlarder.db import Session
from openlarder.models import (
    Group,
    GroupInvite,
    GroupMember,
    LarderList,
    LarderListGroup,
    RecipeNote,
    RecipeNoteGroup,
    SavedGroup,
    ShelfGroup,
    Source,
    SourceGroup,
    User,
)

router = APIRouter(tags=["groups"])

INVITE_DAYS = 7
Role = Literal["view", "edit", "admin"]


class GroupIn(BaseModel):
    name: str = Field(max_length=100)


class GroupSummary(BaseModel):
    id: uuid.UUID
    name: str
    # Your role in it.
    role: Role
    members: int


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str | None
    role: Role


class InviteOut(BaseModel):
    id: uuid.UUID
    role: Role
    expires_at: datetime


class SharedOut(BaseModel):
    id: uuid.UUID
    title: str
    owner_name: str | None


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    role: Role
    members: list[MemberOut]
    # Invites not yet used or expired; for the group's admins only.
    invites: list[InviteOut]
    # The collections shared with it.
    collections: list[SharedOut]


class InviteIn(BaseModel):
    role: Role = "view"


class NewInvite(InviteOut):
    # Shown once: the link is /invite/<token>.
    token: str


class RoleIn(BaseModel):
    role: Role


class InviteInfo(BaseModel):
    group: str
    role: Role


def _name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the group a name.")
    return name


async def _membership(session: Session, group_id: uuid.UUID, user: User) -> GroupMember:
    """The user's membership; a group they aren't in doesn't exist for them."""
    member = await session.get(GroupMember, (group_id, user.id))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such group.")
    return member


async def _as_admin(session: Session, group_id: uuid.UUID, user: User) -> GroupMember:
    member = await _membership(session, group_id, user)
    if member.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the group's admins can do that.")
    return member


async def _admins(session: Session, group_id: uuid.UUID) -> int:
    return await session.scalar(
        select(func.count()).where(GroupMember.group_id == group_id, GroupMember.role == "admin")
    )


LAST_ADMIN = "A group needs an admin: make someone else one first, or delete the group."


async def _unshare(session: Session, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Stop sharing someone's collections, larder lists, shelf, saved
    recipes and notes with a group they've left."""
    await session.execute(
        delete(SourceGroup).where(
            SourceGroup.group_id == group_id,
            SourceGroup.source_id.in_(select(Source.id).where(Source.owner_id == user_id)),
        )
    )
    await session.execute(
        delete(LarderListGroup).where(
            LarderListGroup.group_id == group_id,
            LarderListGroup.list_id.in_(
                select(LarderList.id).where(LarderList.owner_id == user_id)
            ),
        )
    )
    await session.execute(
        delete(ShelfGroup).where(ShelfGroup.group_id == group_id, ShelfGroup.user_id == user_id)
    )
    await session.execute(
        delete(SavedGroup).where(SavedGroup.group_id == group_id, SavedGroup.user_id == user_id)
    )
    await session.execute(
        delete(RecipeNoteGroup).where(
            RecipeNoteGroup.group_id == group_id,
            RecipeNoteGroup.note_id.in_(select(RecipeNote.id).where(RecipeNote.user_id == user_id)),
        )
    )


@router.get("/api/groups", response_model=list[GroupSummary])
async def my_groups(user: CurrentUser, session: Session) -> list[GroupSummary]:
    size = (
        select(func.count())
        .where(GroupMember.group_id == Group.id)
        .correlate(Group)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Group.id, Group.name, GroupMember.role, size)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user.id)
        .order_by(func.lower(Group.name), Group.id)
    )
    return [GroupSummary(id=i, name=n, role=r, members=c) for i, n, r, c in rows]


@router.post(
    "/api/groups",
    response_model=GroupSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def make_group(body: GroupIn, user: CurrentUser, session: Session) -> GroupSummary:
    """A new group, with its maker as its admin."""
    group = Group(name=_name(body.name))
    session.add(group)
    await session.flush()
    session.add(GroupMember(group_id=group.id, user_id=user.id, role="admin"))
    await session.commit()
    return GroupSummary(id=group.id, name=group.name, role="admin", members=1)


@router.get("/api/groups/{group_id}", response_model=GroupOut)
async def get_group(group_id: uuid.UUID, user: CurrentUser, session: Session) -> GroupOut:
    me = await _membership(session, group_id, user)
    group = await session.get_one(Group, group_id)
    members = await session.execute(
        select(User.id, User.display_name, GroupMember.role)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
        .order_by(func.lower(func.coalesce(User.display_name, "")), User.id)
    )
    invites = []
    if me.role == "admin":
        invites = (
            await session.scalars(
                select(GroupInvite)
                .where(
                    GroupInvite.group_id == group_id,
                    GroupInvite.used_at.is_(None),
                    GroupInvite.expires_at > func.now(),
                )
                .order_by(GroupInvite.created_at)
            )
        ).all()
    collections = await session.execute(
        select(Source.id, Source.title, User.display_name)
        .join(SourceGroup, SourceGroup.source_id == Source.id)
        .outerjoin(User, User.id == Source.owner_id)
        .where(SourceGroup.group_id == group_id)
        .order_by(func.lower(Source.title), Source.id)
    )
    return GroupOut(
        id=group.id,
        name=group.name,
        role=me.role,
        members=[MemberOut(user_id=i, name=n, role=r) for i, n, r in members],
        invites=[InviteOut(id=x.id, role=x.role, expires_at=x.expires_at) for x in invites],
        collections=[SharedOut(id=i, title=t, owner_name=n) for i, t, n in collections],
    )


@router.patch("/api/groups/{group_id}", response_model=GroupSummary, dependencies=[SameOrigin])
async def rename_group(
    group_id: uuid.UUID, body: GroupIn, user: CurrentUser, session: Session
) -> GroupSummary:
    await _as_admin(session, group_id, user)
    group = await session.get_one(Group, group_id)
    group.name = _name(body.name)
    await session.commit()
    count = await session.scalar(select(func.count()).where(GroupMember.group_id == group_id))
    return GroupSummary(id=group.id, name=group.name, role="admin", members=count)


@router.delete(
    "/api/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SameOrigin]
)
async def delete_group(group_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    """Delete a group: its members, invites and sharing go with it; the
    collections themselves stay with their owners."""
    await _as_admin(session, group_id, user)
    await session.delete(await session.get_one(Group, group_id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/groups/{group_id}/invites",
    response_model=NewInvite,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def invite(
    group_id: uuid.UUID, body: InviteIn, user: CurrentUser, session: Session
) -> NewInvite:
    """A link for one person to join with this role. The token is in this
    answer only."""
    await _as_admin(session, group_id, user)
    token = new_token()
    made = GroupInvite(
        group_id=group_id,
        token_hash=hash_token(token),
        role=body.role,
        created_by=user.id,
        expires_at=func.now() + timedelta(days=INVITE_DAYS),
    )
    session.add(made)
    await session.commit()
    await session.refresh(made)
    return NewInvite(id=made.id, role=made.role, expires_at=made.expires_at, token=token)


@router.delete(
    "/api/groups/{group_id}/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SameOrigin],
)
async def cancel_invite(
    group_id: uuid.UUID, invite_id: uuid.UUID, user: CurrentUser, session: Session
) -> Response:
    await _as_admin(session, group_id, user)
    found = await session.get(GroupInvite, invite_id)
    if found is None or found.group_id != group_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such invite.")
    await session.delete(found)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/api/groups/{group_id}/members/{user_id}",
    response_model=MemberOut,
    dependencies=[SameOrigin],
)
async def set_role(
    group_id: uuid.UUID, user_id: uuid.UUID, body: RoleIn, user: CurrentUser, session: Session
) -> MemberOut:
    await _as_admin(session, group_id, user)
    member = await session.get(GroupMember, (group_id, user_id))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "They aren't in this group.")
    if member.role == "admin" and body.role != "admin" and await _admins(session, group_id) == 1:
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_ADMIN)
    member.role = body.role
    await session.commit()
    person = await session.get_one(User, user_id)
    return MemberOut(user_id=user_id, name=person.display_name, role=member.role)


@router.delete(
    "/api/groups/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SameOrigin],
)
async def remove_member(
    group_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: Session
) -> Response:
    """Leave a group (your own ID), or, as its admin, remove someone."""
    me = await _membership(session, group_id, user)
    if user_id != user.id and me.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the group's admins can do that.")
    member = await session.get(GroupMember, (group_id, user_id))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "They aren't in this group.")
    if member.role == "admin" and await _admins(session, group_id) == 1:
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_ADMIN)
    await session.delete(member)
    await _unshare(session, group_id, user_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _open_invite(session: Session, token: str) -> tuple[GroupInvite, Group]:
    found = await session.scalar(
        select(GroupInvite).where(GroupInvite.token_hash == hash_token(token))
    )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That invite link isn't one of ours.")
    if found.used_at is not None or found.expires_at <= await session.scalar(select(func.now())):
        raise HTTPException(
            status.HTTP_410_GONE,
            "That invite has been used or has expired. Ask for a new one.",
        )
    return found, await session.get_one(Group, found.group_id)


# The link's token is called code here: the session cookie's parameter is
# already called token.
@router.get("/api/invites/{code}", response_model=InviteInfo)
async def read_invite(code: str, session: Session) -> InviteInfo:
    """What an invite link is for, so its page can say before joining."""
    found, group = await _open_invite(session, code)
    return InviteInfo(group=group.name, role=found.role)


@router.post("/api/invites/{code}/accept", response_model=GroupSummary, dependencies=[SameOrigin])
async def accept_invite(code: str, user: CurrentUser, session: Session) -> GroupSummary:
    found, group = await _open_invite(session, code)
    if await session.get(GroupMember, (group.id, user.id)) is not None:
        # Left unused, for whoever it was meant for.
        raise HTTPException(status.HTTP_409_CONFLICT, f"You're already in {group.name}.")
    # Claimed in one statement, so two people opening it at once can't both
    # get in.
    claimed = await session.scalar(
        update(GroupInvite)
        .where(GroupInvite.id == found.id, GroupInvite.used_at.is_(None))
        .values(used_at=func.now(), used_by=user.id)
        .returning(GroupInvite.id)
    )
    if claimed is None:
        raise HTTPException(status.HTTP_410_GONE, "That invite has just been used.")
    session.add(GroupMember(group_id=group.id, user_id=user.id, role=found.role))
    await session.commit()
    count = await session.scalar(select(func.count()).where(GroupMember.group_id == group.id))
    return GroupSummary(id=group.id, name=group.name, role=found.role, members=count)
