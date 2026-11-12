"""Your shelf: the books you own (migration 0062). *SCOPING.md: "mark books
you own, filter search to your shelf".*

A book goes on your shelf from its page, with the edition you have if it
has several, so a recipe's page opens at your edition's page number.
Search's "Only my shelf" (routers/search.py, shelf=true) keeps to them.
Books only: a website or a show isn't something you own a copy of.

Private, like the larder: only you see it, and it isn't in the edit
history, the dumps or the API's public reads. A book you can no longer see
(a private one unshared from you) drops out of it, and comes back if you
can see it again.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from openlarder import visibility
from openlarder.auth import CurrentUser, SameOrigin
from openlarder.db import Session
from openlarder.models import Edition, ShelfBook, Source, User
from openlarder.routers.sources import BookSummary, summaries

router = APIRouter(prefix="/api/shelf", tags=["shelf"])
# More than any kitchen holds; a bound on what one person's rows can grow to.
MAX_BOOKS = 5000


class OnShelf(BaseModel):
    source_id: uuid.UUID
    on_shelf: bool
    # The edition you have, if you've said.
    edition_id: uuid.UUID | None = None


class ShelfEntry(BookSummary):
    edition_id: uuid.UUID | None
    # The edition you have, as its year and ISBN, when you've said.
    edition_year: int | None = None
    edition_isbn13: str | None = None
    added_at: datetime


class Shelf(BaseModel):
    books: list[ShelfEntry]


class ShelfIn(BaseModel):
    edition_id: uuid.UUID | None = None


def shelf_source_ids(user: User):
    """The books on someone's shelf that they can still see."""
    return (
        select(ShelfBook.source_id)
        .join(Source, Source.id == ShelfBook.source_id)
        .where(ShelfBook.user_id == user.id, visibility.sources_seen_by(user))
    )


@router.get("", response_model=Shelf)
async def mine(user: CurrentUser, session: Session) -> Shelf:
    rows = (
        await session.execute(
            select(Source, ShelfBook, Edition)
            .join(ShelfBook, ShelfBook.source_id == Source.id)
            .outerjoin(Edition, Edition.id == ShelfBook.edition_id)
            .where(ShelfBook.user_id == user.id, visibility.sources_seen_by(user))
            .order_by(func.lower(Source.title), Source.id)
        )
    ).all()
    cards = await summaries(session, [s for s, _, _ in rows])
    return Shelf(
        books=[
            ShelfEntry(
                **card.model_dump(),
                edition_id=shelved.edition_id,
                edition_year=edition.published_year if edition else None,
                edition_isbn13=edition.isbn13 if edition else None,
                added_at=shelved.created_at,
            )
            for card, (_, shelved, edition) in zip(cards, rows, strict=True)
        ]
    )


async def _seen_book(session, user: User, source_id: uuid.UUID) -> Source:
    source = await session.scalar(
        select(Source).where(Source.id == source_id, visibility.sources_seen_by(user))
    )
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    if source.kind != "book":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Only books go on a shelf.")
    return source


@router.get("/{source_id}", response_model=OnShelf)
async def one(source_id: uuid.UUID, user: CurrentUser, session: Session) -> OnShelf:
    """Whether a book is on your shelf, and which edition."""
    row = await session.scalar(
        select(ShelfBook).where(
            ShelfBook.user_id == user.id,
            ShelfBook.source_id == source_id,
            ShelfBook.source_id.in_(shelf_source_ids(user)),
        )
    )
    if row is None:
        return OnShelf(source_id=source_id, on_shelf=False)
    return OnShelf(source_id=source_id, on_shelf=True, edition_id=row.edition_id)


@router.put("/{source_id}", response_model=OnShelf, dependencies=[SameOrigin])
async def put(source_id: uuid.UUID, body: ShelfIn, user: CurrentUser, session: Session) -> OnShelf:
    """Put a book on your shelf, or change which edition you have."""
    source = await _seen_book(session, user, source_id)
    if body.edition_id is not None:
        edition = await session.get(Edition, body.edition_id)
        if edition is None or edition.source_id != source.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "That edition isn't one of this book's."
            )
    row = await session.get(ShelfBook, (user.id, source.id))
    if row is None:
        held = await session.scalar(
            select(func.count()).select_from(ShelfBook).where(ShelfBook.user_id == user.id)
        )
        if held >= MAX_BOOKS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"A shelf holds at most {MAX_BOOKS:,} books.",
            )
        row = ShelfBook(user_id=user.id, source_id=source.id)
        session.add(row)
    row.edition_id = body.edition_id
    await session.commit()
    return OnShelf(source_id=source.id, on_shelf=True, edition_id=row.edition_id)


@router.delete("/{source_id}", status_code=204, dependencies=[SameOrigin])
async def remove(source_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    await session.execute(
        delete(ShelfBook).where(ShelfBook.user_id == user.id, ShelfBook.source_id == source_id)
    )
    await session.commit()
    return Response(status_code=204)
