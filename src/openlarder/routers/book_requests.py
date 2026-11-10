"""Requests for a book to be indexed: asking, voting, claiming. *Ray,
2026-11-09.*

Anyone asks, signed in or not, by ISBN (looked up on Open Library) or by
title. A book already asked for gets a vote instead, one per person or per
address; one already in the catalog with recipes is pointed to. Signed-out
asking is limited per address, and a field people never see catches bots.
An address is kept only as its pseudonym (usage.py), to count one vote.

Contributors (roles.py) and those above them claim a request to queue it up.
A claim doesn't stop anyone entering the book sooner, and lapses after
CLAIM_LAPSES with nothing done: it reads as open again, and anyone may
claim it. A contributor releases a claim, or marks it done; a moderator
declines a request, saying why.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.exc import IntegrityError

from openlarder import isbn, openlibrary, usage
from openlarder.auth import CurrentUser, ModeratorUser, SameOrigin, Viewer
from openlarder.db import Session
from openlarder.models import BookRequest, Edition, Recipe, RequestVote, Source, User
from openlarder.ratelimit import _address
from openlarder.routers.sources import Transport

router = APIRouter(tags=["requests"])
CLAIM_LAPSES = timedelta(days=30)
# Requests a day from one address, signed out.
ANONYMOUS_PER_DAY = 5
_asked: dict[str, tuple[str, int]] = {}


def reset() -> None:
    """Forget the day's counts (tests)."""
    _asked.clear()


class Person(BaseModel):
    id: uuid.UUID
    name: str | None


class RequestOut(BaseModel):
    id: uuid.UUID
    isbn13: str | None
    title: str
    author: str | None
    note: str | None
    source_id: uuid.UUID | None
    # As it reads now: a lapsed claim is open.
    status: Literal["open", "claimed", "done", "declined"]
    votes: int
    created_at: datetime
    claimed_by: Person | None
    claimed_at: datetime | None
    reason: str | None
    # Whether the viewer has asked for or voted for it already.
    voted: bool = False
    mine: bool = False


class RequestPage(BaseModel):
    requests: list[RequestOut]
    counts: dict[str, int]


def _lapsed():
    return and_(BookRequest.status == "claimed", BookRequest.active_at < func.now() - CLAIM_LAPSES)


def _status():
    """The status as it reads: a claim quiet too long is open."""
    return case((_lapsed(), "open"), else_=BookRequest.status)


def _voter(request: Request, viewer: User | None) -> str:
    return f"user:{viewer.id}" if viewer else f"ip:{usage.pseudonym(_address(request))}"


async def _out(
    session, rows: list[BookRequest], voter: str, viewer: User | None
) -> list[RequestOut]:
    ids = [r.id for r in rows]
    voted = set(
        await session.scalars(
            select(RequestVote.request_id).where(
                RequestVote.request_id.in_(ids), RequestVote.voter == voter
            )
        )
    )
    claimers = dict(
        (
            await session.execute(
                select(User.id, User.display_name).where(
                    User.id.in_({r.claimed_by for r in rows if r.claimed_by})
                )
            )
        ).all()
    )
    now = datetime.now(UTC)
    out = []
    for r in rows:
        lapsed = r.status == "claimed" and r.active_at and now - r.active_at > CLAIM_LAPSES
        out.append(
            RequestOut(
                id=r.id,
                isbn13=r.isbn13,
                title=r.title,
                author=r.author,
                note=r.note,
                source_id=r.source_id,
                status="open" if lapsed else r.status,
                votes=r.votes,
                created_at=r.created_at,
                claimed_by=(
                    None
                    if lapsed or not r.claimed_by
                    else Person(id=r.claimed_by, name=claimers.get(r.claimed_by))
                ),
                claimed_at=None if lapsed else r.claimed_at,
                reason=r.reason,
                voted=r.id in voted,
                mine=bool(viewer and (r.requested_by == viewer.id or r.claimed_by == viewer.id)),
            )
        )
    return out


@router.get("/api/requests", response_model=RequestPage)
async def list_requests(
    request: Request,
    session: Session,
    viewer: Viewer,
    state: Literal["open", "claimed", "done", "declined", "mine"] = "open",
    sort: Literal["votes", "new"] = "votes",
) -> RequestPage:
    """The requests in one state, most wanted (or newest) first; "mine" is
    what the viewer asked for or claimed."""
    query = select(BookRequest)
    if state == "mine":
        if viewer is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to see yours.")
        query = query.where(
            or_(BookRequest.requested_by == viewer.id, BookRequest.claimed_by == viewer.id)
        )
    else:
        query = query.where(_status() == state)
    order = (
        (BookRequest.votes.desc(), BookRequest.created_at)
        if sort == "votes"
        else (BookRequest.created_at.desc(),)
    )
    rows = list(await session.scalars(query.order_by(*order).limit(200)))
    reads = select(_status().label("status")).subquery()
    counts = dict(
        (await session.execute(select(reads.c.status, func.count()).group_by(reads.c.status))).all()
    )
    return RequestPage(
        requests=await _out(session, rows, _voter(request, viewer), viewer), counts=counts
    )


class RequestIn(BaseModel):
    isbn: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=300)
    author: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)
    # Never shown to people; a bot fills it in.
    website: str | None = None


class Asked(BaseModel):
    # created: a new request; voted: added to one already asked for;
    # already: this person or address voted for it before; in_catalog: the
    # book is here with recipes, so nothing is asked.
    outcome: Literal["created", "voted", "already", "in_catalog"]
    request: RequestOut | None = None
    source_id: uuid.UUID | None = None


def _squash(text: str | None) -> str | None:
    return " ".join((text or "").split()) or None


async def _vote(session, row: BookRequest, voter: str) -> bool:
    """Count a vote, once per voter; False if they'd voted already."""
    try:
        async with session.begin_nested():
            session.add(RequestVote(request_id=row.id, voter=voter))
    except IntegrityError:
        return False
    row.votes += 1
    return True


@router.post("/api/requests", response_model=Asked, dependencies=[SameOrigin])
async def ask(
    body: RequestIn, request: Request, session: Session, viewer: Viewer, transport: Transport
) -> Asked:
    voter = _voter(request, viewer)
    if body.website:
        # A bot: answer as if all went well, and keep nothing.
        return Asked(outcome="created")
    if viewer is None:
        today = datetime.now(UTC).date().isoformat()
        day, n = _asked.get(voter, (today, 0))
        n = n if day == today else 0
        if n >= ANONYMOUS_PER_DAY:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"{ANONYMOUS_PER_DAY} requests a day without signing in. Sign in to ask for more.",
            )
        _asked[voter] = (today, n + 1)

    isbn13 = None
    title, author = _squash(body.title), _squash(body.author)
    if body.isbn and body.isbn.strip():
        try:
            isbn13 = isbn.normalise(body.isbn)
        except isbn.InvalidIsbn as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    if isbn13 is None and not title:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the book's ISBN, or its title."
        )

    # Already in the catalog?
    source_id = None
    if isbn13:
        source_id = await session.scalar(
            select(Edition.source_id)
            .join(Source, Source.id == Edition.source_id)
            .where(Edition.isbn13 == isbn13, Source.private.is_(False))
        )
    if source_id and await session.scalar(select(exists().where(Recipe.source_id == source_id))):
        return Asked(outcome="in_catalog", source_id=source_id)

    # Asked for already: a vote.
    same = (
        BookRequest.isbn13 == isbn13 if isbn13 else func.lower(BookRequest.title) == title.lower()
    )
    existing = await session.scalar(
        select(BookRequest).where(same, BookRequest.status.in_(("open", "claimed")))
    )
    if existing is not None:
        counted = await _vote(session, existing, voter)
        await session.commit()
        [out] = await _out(session, [existing], voter, viewer)
        return Asked(outcome="voted" if counted else "already", request=out)

    if isbn13 and not title:
        try:
            found = await openlibrary.find_by_isbn(isbn13, transport)
            title = found.title
            author = author or ", ".join(a.name for a in found.authors) or None
        except (openlibrary.NotFound, openlibrary.Unavailable):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Open Library doesn't know that ISBN. Give the book's title too.",
            ) from None
    row = BookRequest(
        isbn13=isbn13,
        title=title,
        author=author,
        note=_squash(body.note),
        source_id=source_id,
        requested_by=viewer.id if viewer else None,
    )
    session.add(row)
    await session.flush()
    session.add(RequestVote(request_id=row.id, voter=voter))
    await session.commit()
    [out] = await _out(session, [row], voter, viewer)
    return Asked(outcome="created", request=out)


async def _request_or_404(session, request_id: uuid.UUID) -> BookRequest:
    row = await session.get(BookRequest, request_id, with_for_update=True)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such request.")
    return row


async def _one(session, row: BookRequest, request: Request, viewer: User | None) -> RequestOut:
    await session.commit()
    await session.refresh(row)
    [out] = await _out(session, [row], _voter(request, viewer), viewer)
    return out


@router.post(
    "/api/requests/{request_id}/vote", response_model=RequestOut, dependencies=[SameOrigin]
)
async def vote(
    request_id: uuid.UUID, request: Request, session: Session, viewer: Viewer
) -> RequestOut:
    row = await _request_or_404(session, request_id)
    if row.status not in ("open", "claimed"):
        raise HTTPException(status.HTTP_409_CONFLICT, "That request is closed.")
    await _vote(session, row, _voter(request, viewer))
    return await _one(session, row, request, viewer)


def _may_enter(user: User) -> None:
    if not user.may_claim:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only contributors claim requests. A moderator can make you one.",
        )


@router.post(
    "/api/requests/{request_id}/claim", response_model=RequestOut, dependencies=[SameOrigin]
)
async def claim(
    request_id: uuid.UUID, request: Request, user: CurrentUser, session: Session
) -> RequestOut:
    _may_enter(user)
    row = await _request_or_404(session, request_id)
    lapsed = (
        row.status == "claimed"
        and row.active_at
        and (datetime.now(UTC) - row.active_at > CLAIM_LAPSES)
    )
    if row.status == "claimed" and not lapsed and row.claimed_by != user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Someone has claimed it already.")
    if row.status in ("done", "declined"):
        raise HTTPException(status.HTTP_409_CONFLICT, "That request is closed.")
    row.status, row.claimed_by = "claimed", user.id
    row.claimed_at = row.active_at = func.now()
    return await _one(session, row, request, user)


@router.post(
    "/api/requests/{request_id}/release", response_model=RequestOut, dependencies=[SameOrigin]
)
async def release(
    request_id: uuid.UUID, request: Request, user: CurrentUser, session: Session
) -> RequestOut:
    row = await _request_or_404(session, request_id)
    if row.status != "claimed" or not (row.claimed_by == user.id or user.may_edit):
        raise HTTPException(status.HTTP_409_CONFLICT, "It isn't your claim to release.")
    row.status, row.claimed_by, row.claimed_at, row.active_at = "open", None, None, None
    return await _one(session, row, request, user)


class Done(BaseModel):
    # The source it was entered as, if known.
    source_id: uuid.UUID | None = None


@router.post(
    "/api/requests/{request_id}/done", response_model=RequestOut, dependencies=[SameOrigin]
)
async def mark_done(
    request_id: uuid.UUID, body: Done, request: Request, user: CurrentUser, session: Session
) -> RequestOut:
    """The book is entered: by its claimer, or any contributor or above."""
    _may_enter(user)
    row = await _request_or_404(session, request_id)
    if row.status in ("done", "declined"):
        raise HTTPException(status.HTTP_409_CONFLICT, "That request is closed.")
    if body.source_id is not None:
        if await session.get(Source, body.source_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No such source.")
        row.source_id = body.source_id
    row.status, row.claimed_by, row.closed_at = "done", None, func.now()
    return await _one(session, row, request, user)


class Decline(BaseModel):
    reason: str = Field(max_length=300)


@router.post(
    "/api/requests/{request_id}/decline", response_model=RequestOut, dependencies=[SameOrigin]
)
async def decline(
    request_id: uuid.UUID, body: Decline, request: Request, admin: ModeratorUser, session: Session
) -> RequestOut:
    """A moderator turns a request down, saying why (not a cookbook, a duplicate)."""
    reason = _squash(body.reason)
    if not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Say why it's declined.")
    row = await _request_or_404(session, request_id)
    if row.status in ("done", "declined"):
        raise HTTPException(status.HTTP_409_CONFLICT, "That request is closed.")
    row.status, row.claimed_by, row.reason, row.closed_at = "declined", None, reason, func.now()
    return await _one(session, row, request, admin)
