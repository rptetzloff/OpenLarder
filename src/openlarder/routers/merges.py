"""Merged books, for administrators: each merge, and taking one apart
again (book_merge.unmerge). *Ray, 2026-11-11: "even if admin only as a
check on moderators".*"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import aliased

from openlarder import book_merge, history
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import BookMerge, Source, User

router = APIRouter(prefix="/api/merges", tags=["merges"])
log = logging.getLogger(__name__)


class Book(BaseModel):
    id: uuid.UUID
    title: str


class MergeOut(BaseModel):
    id: uuid.UUID
    gone: Book
    # The book kept, while it exists.
    kept: Book | None
    # What moved.
    editions: int
    recipes: int
    merged_by: str | None
    merged_at: datetime
    undone_by: str | None
    undone_at: datetime | None


@router.get("", response_model=list[MergeOut])
async def merges(admin: AdminUser, session: Session) -> list[MergeOut]:
    """Every merge of two books, newest first."""
    merger, undoer = aliased(User), aliased(User)
    rows = await session.execute(
        select(BookMerge, Source.title, merger.display_name, undoer.display_name)
        .outerjoin(Source, Source.id == BookMerge.kept_id)
        .outerjoin(merger, merger.id == BookMerge.merged_by)
        .outerjoin(undoer, undoer.id == BookMerge.undone_by)
        .order_by(BookMerge.merged_at.desc())
        .limit(500)
    )
    return [
        MergeOut(
            id=m.id,
            gone=Book(id=m.gone_id, title=m.gone_title),
            kept=Book(id=m.kept_id, title=kept) if kept is not None else None,
            editions=len(m.saved.get("editions", [])),
            recipes=len(m.saved.get("recipes", [])),
            merged_by=by,
            merged_at=m.merged_at,
            undone_by=undone_by,
            undone_at=m.undone_at,
        )
        for m, kept, by, undone_by in rows
    ]


class Unmerged(BaseModel):
    # The book put back.
    id: uuid.UUID


@router.post("/{merge_id}/unmerge", response_model=Unmerged, dependencies=[SameOrigin])
async def unmerge(merge_id: uuid.UUID, admin: AdminUser, session: Session) -> Unmerged:
    record = await session.get(BookMerge, merge_id, with_for_update=True)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such merge.")
    await history.via(session, f"unmerge:{record.gone_id}")
    try:
        book = await book_merge.unmerge(session, record, admin)
    except book_merge.CantMerge as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    await session.commit()
    log.info("%s unmerged book %s from %s", admin.id, record.gone_id, record.kept_id)
    return Unmerged(id=book.id)
