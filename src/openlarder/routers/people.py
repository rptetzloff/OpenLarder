"""People and their roles, for moderators and above (roles.py).

*Ray, 2026-11-10:* user, contributor, moderator, administrator, owner. A
moderator makes contributors, an administrator makes moderators, and only
the owner makes administrators. No one changes their own role, and the
owner's is set only in the database.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from openlarder import roles
from openlarder.auth import ModeratorUser, SameOrigin
from openlarder.db import Session
from openlarder.models import BookRequest, User

router = APIRouter(prefix="/api/admin/people", tags=["people"])
# Who can give or take away a role, by the role just above it.
WHO = {"moderator": "a moderator", "admin": "an administrator", "owner": "the owner"}


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str | None
    role: roles.Role
    # Requests they hold a claim on.
    claims: int
    created_at: datetime
    # Whether the one asking may change this person's role.
    changeable: bool
    # earned, granted or withheld (trust.py); none yet.
    trust: str | None = None


def _claims():
    return (
        select(func.count())
        .where(BookRequest.claimed_by == User.id, BookRequest.status == "claimed")
        .correlate(User)
        .scalar_subquery()
    )


def _out(me: User, person: User, claims: int) -> PersonOut:
    return PersonOut(
        id=person.id,
        name=person.display_name,
        role=person.role,  # type: ignore[arg-type]
        claims=claims,
        created_at=person.created_at,
        changeable=person.id != me.id and person.role in roles.grantable(me.role),
        trust=person.trust,
    )


@router.get("", response_model=list[PersonOut])
async def people(
    me: ModeratorUser,
    session: Session,
    q: str = Query("", max_length=100),
    role: roles.Role | None = None,
) -> list[PersonOut]:
    """Found by name; with no name, everyone above user (or in one role),
    highest first."""
    query = select(User, _claims())
    words = q.strip()
    if words:
        query = query.where(User.display_name.ilike(f"%{words}%"))
    elif role:
        query = query.where(User.role == role)
    else:
        query = query.where(User.role != "user")
    rows = (await session.execute(query.limit(200))).all()
    found = [_out(me, u, n) for u, n in rows]
    found.sort(key=lambda p: (-roles.rank(p.role), (p.name or "").lower()))
    return found[:50]


class RoleIn(BaseModel):
    role: roles.Role


@router.put("/{user_id}/role", response_model=PersonOut, dependencies=[SameOrigin])
async def set_role(
    user_id: uuid.UUID, body: RoleIn, me: ModeratorUser, session: Session
) -> PersonOut:
    person = await session.get(User, user_id, with_for_update=True)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such person.")
    if person.id == me.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't change your own role.")
    if "owner" in (person.role, body.role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "The owner is set in the database, not from the site."
        )
    allowed = roles.grantable(me.role)
    if person.role not in allowed or body.role not in allowed:
        needed = roles.LADDER[max(roles.rank(person.role), roles.rank(body.role)) + 1]
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Only {WHO[needed]} can do that.")
    person.role = body.role
    await session.commit()
    claims = await session.scalar(
        select(func.count()).where(
            BookRequest.claimed_by == user_id, BookRequest.status == "claimed"
        )
    )
    return _out(me, person, claims or 0)


class TrustIn(BaseModel):
    # granted, withheld, or none to clear it (and let it be earned again).
    trust: Literal["granted", "withheld"] | None


@router.put("/{user_id}/trust", response_model=PersonOut, dependencies=[SameOrigin])
async def set_trust(
    user_id: uuid.UUID, body: TrustIn, me: ModeratorUser, session: Session
) -> PersonOut:
    """A moderator trusts a contributor by hand, or withholds it; withheld
    isn't earned back by itself (trust.py)."""
    person = await session.get(User, user_id, with_for_update=True)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such person.")
    if person.id == me.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't change your own trust.")
    if person.role != "contributor":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Trust is a contributor's: moderators and up publish anyway."
        )
    person.trust = body.trust
    person.trust_set_at, person.trust_set_by = func.now(), me.id
    await session.commit()
    await session.refresh(person)
    claims = await session.scalar(
        select(func.count()).where(
            BookRequest.claimed_by == user_id, BookRequest.status == "claimed"
        )
    )
    return _out(me, person, claims or 0)
