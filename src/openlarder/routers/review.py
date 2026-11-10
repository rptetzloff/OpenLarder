"""Review: moderators approve what contributors add, or send it back with
a reason (migration 0041). *Ray, 2026-11-10:* each book and recipe on its
own, with an "approve all" for a book; one sent back waits for its
contributor to fix it, and is waiting again once they change it.

Also the contributor's side: what of theirs is waiting or was sent back,
and the agreement they accept before adding anything.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update

from openlarder import agreement
from openlarder.auth import CurrentUser, ModeratorUser, SameOrigin
from openlarder.db import Session
from openlarder.models import BookRequest, Edition, Proposal, Recipe, Source, User

router = APIRouter(tags=["review"])
WAITING = ("pending", "returned")


class Item(BaseModel):
    id: uuid.UUID
    title: str
    review: str
    review_note: str | None
    by: str | None
    created_at: datetime


class Group(BaseModel):
    """A source, and its recipes waiting for review."""

    source: Item
    kind: str
    recipes: list[Item]


class Queue(BaseModel):
    groups: list[Group]
    # Waiting for a moderator: books and recipes (not those sent back) and
    # proposed changes.
    pending: int


async def _names(session, ids) -> dict[uuid.UUID, str | None]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict(
        (await session.execute(select(User.id, User.display_name).where(User.id.in_(ids)))).all()
    )


def _item(row: Source | Recipe, names) -> Item:
    return Item(
        id=row.id,
        title=row.title,
        review=row.review,
        review_note=row.review_note,
        by=names.get(row.created_by),
        created_at=row.created_at,
    )


async def _groups(session, source_filter, recipe_filter) -> list[Group]:
    recipes = list(
        await session.scalars(
            select(Recipe).where(recipe_filter).order_by(Recipe.created_at).limit(500)
        )
    )
    sources = list(
        await session.scalars(
            select(Source)
            .where(or_(source_filter, Source.id.in_({r.source_id for r in recipes})))
            .order_by(Source.created_at)
            .limit(500)
        )
    )
    names = await _names(session, [r.created_by for r in recipes] + [s.created_by for s in sources])
    by_source: dict[uuid.UUID, list[Item]] = {}
    for r in recipes:
        by_source.setdefault(r.source_id, []).append(_item(r, names))
    return [
        Group(source=_item(s, names), kind=s.kind, recipes=by_source.get(s.id, [])) for s in sources
    ]


@router.get("/api/review", response_model=Queue)
async def queue(moderator: ModeratorUser, session: Session) -> Queue:
    """Everything waiting or sent back, by source, oldest first."""
    groups = await _groups(
        session,
        Source.review.in_(WAITING),
        Recipe.review.in_(WAITING),
    )
    pending = (
        (await session.scalar(select(func.count()).where(Source.review == "pending")))
        + await session.scalar(select(func.count()).where(Recipe.review == "pending"))
        + await session.scalar(select(func.count()).where(Proposal.status == "open"))
    )
    return Queue(groups=groups, pending=pending)


class Decision(BaseModel):
    action: Literal["approve", "return"]
    # Why it's sent back; the contributor reads it.
    note: str | None = Field(default=None, max_length=500)


def _decide(row: Source | Recipe, body: Decision, moderator: User) -> None:
    if row.review == "published":
        raise HTTPException(status.HTTP_409_CONFLICT, "That's published already.")
    if body.action == "return":
        note = " ".join((body.note or "").split())
        if not note:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Say what needs fixing, for the contributor."
            )
        row.review, row.review_note = "returned", note
    else:
        row.review, row.review_note = "published", None
    row.reviewed_by, row.reviewed_at = moderator.id, func.now()


async def _close_requests(session, source: Source) -> None:
    """A book now published closes the requests for it (routers/book_requests.py)."""
    isbns = select(Edition.isbn13).where(
        Edition.source_id == source.id, Edition.isbn13.is_not(None)
    )
    await session.execute(
        update(BookRequest)
        .where(BookRequest.isbn13.in_(isbns), BookRequest.status.in_(("open", "claimed")))
        .values(status="done", source_id=source.id, claimed_by=None, closed_at=func.now())
    )


async def _source(session, source_id: uuid.UUID) -> Source:
    source = await session.get(Source, source_id, with_for_update=True)
    if source is None or source.kind == "family":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such source.")
    return source


@router.post("/api/review/sources/{source_id}", response_model=Item, dependencies=[SameOrigin])
async def decide_source(
    source_id: uuid.UUID, body: Decision, moderator: ModeratorUser, session: Session
) -> Item:
    source = await _source(session, source_id)
    _decide(source, body, moderator)
    await session.flush()
    if source.review == "published":
        await _close_requests(session, source)
    await session.commit()
    await session.refresh(source)
    return _item(source, await _names(session, [source.created_by]))


@router.post("/api/review/recipes/{recipe_id}", response_model=Item, dependencies=[SameOrigin])
async def decide_recipe(
    recipe_id: uuid.UUID, body: Decision, moderator: ModeratorUser, session: Session
) -> Item:
    recipe = await session.get(Recipe, recipe_id, with_for_update=True)
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe.")
    _decide(recipe, body, moderator)
    await session.commit()
    await session.refresh(recipe)
    return _item(recipe, await _names(session, [recipe.created_by]))


class Approved(BaseModel):
    source: bool
    recipes: int


@router.post(
    "/api/review/sources/{source_id}/approve-all",
    response_model=Approved,
    dependencies=[SameOrigin],
)
async def approve_all(source_id: uuid.UUID, moderator: ModeratorUser, session: Session) -> Approved:
    """The source, if it's waiting, and every recipe of it that's waiting;
    those sent back stay with their contributor."""
    source = await _source(session, source_id)
    published_source = source.review == "pending"
    if published_source:
        _decide(source, Decision(action="approve"), moderator)
    result = await session.execute(
        update(Recipe)
        .where(Recipe.source_id == source.id, Recipe.review == "pending")
        .values(
            review="published", review_note=None, reviewed_by=moderator.id, reviewed_at=func.now()
        )
    )
    await session.flush()
    if published_source:
        await _close_requests(session, source)
    await session.commit()
    return Approved(source=published_source, recipes=result.rowcount)


# The contributor's side


@router.get("/api/account/contributions", response_model=list[Group])
async def mine(user: CurrentUser, session: Session) -> list[Group]:
    """What you've added that's waiting for review or was sent back."""
    return await _groups(
        session,
        (Source.created_by == user.id) & Source.review.in_(WAITING),
        (Recipe.created_by == user.id) & Recipe.review.in_(WAITING),
    )


class AgreementOut(BaseModel):
    version: str
    points: list[str]


@router.get("/api/agreement", response_model=AgreementOut)
async def read_agreement() -> AgreementOut:
    return AgreementOut(version=agreement.VERSION, points=agreement.POINTS)


class Accept(BaseModel):
    version: str


@router.post("/api/account/agreement", status_code=204, dependencies=[SameOrigin])
async def accept(body: Accept, user: CurrentUser, session: Session) -> None:
    """Accept the agreement as it reads now; an older version's acceptance
    doesn't count, so the page asks again."""
    if body.version != agreement.VERSION:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The agreement has changed. Read it again before accepting."
        )
    user.agreed_at, user.agreed_version = func.now(), agreement.VERSION
    await session.commit()
