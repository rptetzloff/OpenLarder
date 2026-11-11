"""Reports: "Report a problem" on any public record, for anyone. *Ray,
2026-11-10.*

A report names the record (a recipe, source, ingredient or author, which
the reporter can see), a reason and a note. Signed out, it's limited per
address like book requests, a field people never see catches bots, and the
address is kept only as its pseudonym (usage.py). A second report of the
same record from the same person, while the first is open, replaces it.

Moderators see the open ones, oldest first, with what each is about (or
that it's gone, merged or removed, or one they can't see), and resolve or
dismiss each, saying what they did or why not.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from openlarder import daily, usage, visibility
from openlarder.auth import ModeratorUser, SameOrigin, Viewer
from openlarder.db import Session
from openlarder.models import Author, Ingredient, Recipe, Report, Source, User
from openlarder.ratelimit import _address

router = APIRouter(tags=["reports"])
Kind = Literal["recipe", "source", "ingredient", "author"]
Reason = Literal["wrong", "duplicate", "copied", "spam", "other"]
# Reports a day from one address, signed out; one account, signed in.
ANONYMOUS_PER_DAY = 5
SIGNED_IN_PER_DAY = 50
HREF = {
    "recipe": "/recipes/",
    "source": "/sources/",
    "ingredient": "/ingredients/",
    "author": "/authors/",
}


async def _title(session, viewer: User | None, kind: str, target_id: uuid.UUID) -> str | None:
    """What the record is called, if it's there and the viewer may see it."""
    if kind == "recipe":
        query = select(Recipe.title).where(
            Recipe.id == target_id, visibility.recipes_seen_by(viewer)
        )
    elif kind == "source":
        query = select(Source.title).where(
            Source.id == target_id, visibility.sources_seen_by(viewer)
        )
    elif kind == "ingredient":
        query = select(Ingredient.name).where(
            Ingredient.id == target_id, visibility.ingredients_seen_by(viewer)
        )
    else:
        query = select(Author.name).where(
            Author.id == target_id, visibility.authors_seen_by(viewer)
        )
    return await session.scalar(query)


class ReportIn(BaseModel):
    kind: Kind
    id: uuid.UUID
    reason: Reason
    note: str | None = Field(default=None, max_length=1000)
    # Never shown to people; a bot fills it in.
    website: str | None = None


class Sent(BaseModel):
    ok: bool = True


@router.post("/api/reports", response_model=Sent, status_code=201, dependencies=[SameOrigin])
async def send(body: ReportIn, request: Request, session: Session, viewer: Viewer) -> Sent:
    if body.website:
        return Sent()
    if await _title(session, viewer, body.kind, body.id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's nothing there to report.")
    reporter = f"user:{viewer.id}" if viewer else f"ip:{usage.pseudonym(_address(request))}"
    limit = SIGNED_IN_PER_DAY if viewer else ANONYMOUS_PER_DAY
    if not await daily.take(session, "report", reporter, limit):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"{limit} reports a day"
            + ("." if viewer else " without signing in. Sign in to send more."),
        )
    note = " ".join((body.note or "").split()) or None
    row = await session.scalar(
        select(Report).where(
            Report.target_kind == body.kind,
            Report.target_id == body.id,
            Report.reporter == reporter,
            Report.status == "open",
        )
    )
    if row is None:
        row = Report(
            target_kind=body.kind,
            target_id=body.id,
            reporter=reporter,
            reporter_id=viewer.id if viewer else None,
            reason=body.reason,
        )
        session.add(row)
    row.reason, row.note = body.reason, note
    await session.commit()
    return Sent()


class ReportOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    target_id: uuid.UUID
    # What it's about, as the moderator may see it; none if it's gone or
    # isn't theirs to see.
    title: str | None
    href: str | None
    reason: Reason
    note: str | None
    # The reporter's display name, or none for someone signed out.
    by: str | None
    status: str
    resolution: str | None
    created_at: datetime
    # Other open reports of the same record.
    others: int


class ReportPage(BaseModel):
    reports: list[ReportOut]
    counts: dict[str, int]


@router.get("/api/admin/reports", response_model=ReportPage)
async def queue(
    moderator: ModeratorUser,
    session: Session,
    state: Literal["open", "resolved", "dismissed"] = Query("open"),
) -> ReportPage:
    rows = list(
        await session.scalars(
            select(Report)
            .where(Report.status == state)
            .order_by(Report.created_at if state == "open" else Report.resolved_at.desc())
            .limit(200)
        )
    )
    names = dict(
        (
            await session.execute(
                select(User.id, User.display_name).where(
                    User.id.in_({r.reporter_id for r in rows if r.reporter_id})
                )
            )
        ).all()
    )
    open_per_target = dict(
        (
            await session.execute(
                select(Report.target_id, func.count())
                .where(Report.status == "open")
                .group_by(Report.target_id)
            )
        ).all()
    )
    out = []
    for r in rows:
        title = await _title(session, moderator, r.target_kind, r.target_id)
        out.append(
            ReportOut(
                id=r.id,
                kind=r.target_kind,  # type: ignore[arg-type]
                target_id=r.target_id,
                title=title,
                href=f"{HREF[r.target_kind]}{r.target_id}" if title else None,
                reason=r.reason,  # type: ignore[arg-type]
                note=r.note,
                by=names.get(r.reporter_id),
                status=r.status,
                resolution=r.resolution,
                created_at=r.created_at,
                others=max(0, open_per_target.get(r.target_id, 0) - (r.status == "open")),
            )
        )
    counts = dict(
        (await session.execute(select(Report.status, func.count()).group_by(Report.status))).all()
    )
    return ReportPage(reports=out, counts=counts)


class Decision(BaseModel):
    action: Literal["resolve", "dismiss"]
    note: str | None = Field(default=None, max_length=500)


@router.post("/api/admin/reports/{report_id}", status_code=204, dependencies=[SameOrigin])
async def decide(
    report_id: uuid.UUID, body: Decision, moderator: ModeratorUser, session: Session
) -> None:
    row = await session.get(Report, report_id, with_for_update=True)
    if row is None or row.status != "open":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such open report.")
    row.status = "resolved" if body.action == "resolve" else "dismissed"
    row.resolution = " ".join((body.note or "").split()) or None
    row.resolved_by, row.resolved_at = moderator.id, func.now()
    await session.commit()
