"""Books: the list, one book, and adding one by ISBN.

Reading is public, because the catalog is open data. Adding is for admins
until review exists (migration 0010); it looks the ISBN up on Open Library
and stores what comes back.
"""

import logging
import uuid
from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from openlarder import isbn, openlibrary
from openlarder.auth import AdminUser, SameOrigin
from openlarder.books import AlreadyIndexed, add_book
from openlarder.db import Session
from openlarder.models import Author, Edition, Recipe, Work, WorkCredit

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/books", tags=["books"])


def openlibrary_transport() -> httpx2.AsyncBaseTransport | None:
    """None means the real Open Library; tests replace this with a fake."""
    return None


Transport = Annotated[httpx2.AsyncBaseTransport | None, Depends(openlibrary_transport)]


class BookSummary(BaseModel):
    id: uuid.UUID
    title: str
    subtitle: str | None
    authors: list[str]
    cover_url: str | None
    editions: int


class Credit(BaseModel):
    author_id: uuid.UUID
    credited_as: str
    role: str


class EditionOut(BaseModel):
    id: uuid.UUID
    title: str | None
    isbn13: str | None
    publisher: str | None
    published_year: int | None
    cover_url: str | None
    open_library_url: str | None


class RecipeSummary(BaseModel):
    id: uuid.UUID
    title: str


class Book(BaseModel):
    id: uuid.UUID
    title: str
    subtitle: str | None
    credits: list[Credit]
    editions: list[EditionOut]
    recipes: list[RecipeSummary]


class AddByIsbn(BaseModel):
    isbn: str


class Added(BaseModel):
    id: uuid.UUID


def _cover(cover_id: int | None) -> str | None:
    return openlibrary.cover_url(cover_id) if cover_id else None


@router.get("", response_model=list[BookSummary])
async def list_books(session: Session) -> list[BookSummary]:
    works = (await session.scalars(select(Work).order_by(func.lower(Work.title)))).all()
    if not works:
        return []
    ids = [w.id for w in works]
    credits = (
        await session.execute(
            select(WorkCredit.work_id, WorkCredit.credited_as)
            .where(WorkCredit.work_id.in_(ids))
            .order_by(WorkCredit.work_id, WorkCredit.position)
        )
    ).all()
    editions = (
        await session.execute(
            select(Edition.work_id, Edition.open_library_cover_id)
            .where(Edition.work_id.in_(ids))
            .order_by(Edition.work_id, Edition.published_year.desc().nulls_last())
        )
    ).all()
    names: dict[uuid.UUID, list[str]] = {}
    for work_id, name in credits:
        names.setdefault(work_id, []).append(name)
    covers: dict[uuid.UUID, int | None] = {}
    counts: dict[uuid.UUID, int] = {}
    for work_id, cover_id in editions:
        counts[work_id] = counts.get(work_id, 0) + 1
        # The newest edition with a cover stands for the book.
        if covers.get(work_id) is None:
            covers[work_id] = cover_id
    return [
        BookSummary(
            id=w.id,
            title=w.title,
            subtitle=w.subtitle,
            authors=names.get(w.id, []),
            cover_url=_cover(covers.get(w.id)),
            editions=counts.get(w.id, 0),
        )
        for w in works
    ]


@router.get("/{work_id}", response_model=Book)
async def get_book(work_id: uuid.UUID, session: Session) -> Book:
    work = await session.get(Work, work_id)
    if work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    credits = (
        await session.execute(
            select(WorkCredit, Author.id)
            .join(Author, Author.id == WorkCredit.author_id)
            .where(WorkCredit.work_id == work_id)
            .order_by(WorkCredit.position)
        )
    ).all()
    editions = (
        await session.scalars(
            select(Edition)
            .where(Edition.work_id == work_id)
            .order_by(Edition.published_year.desc().nulls_last(), Edition.isbn13)
        )
    ).all()
    recipes = (
        await session.scalars(
            select(Recipe).where(Recipe.work_id == work_id).order_by(func.lower(Recipe.title))
        )
    ).all()
    return Book(
        id=work.id,
        title=work.title,
        subtitle=work.subtitle,
        credits=[
            Credit(author_id=author_id, credited_as=credit.credited_as, role=credit.role)
            for credit, author_id in credits
        ],
        editions=[
            EditionOut(
                id=e.id,
                title=e.title,
                isbn13=e.isbn13,
                publisher=e.publisher,
                published_year=e.published_year,
                cover_url=_cover(e.open_library_cover_id),
                open_library_url=(
                    openlibrary.book_url(e.open_library_edition_id)
                    if e.open_library_edition_id
                    else None
                ),
            )
            for e in editions
        ],
        recipes=[RecipeSummary(id=r.id, title=r.title) for r in recipes],
    )


@router.post(
    "",
    response_model=Added,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def add_by_isbn(
    body: AddByIsbn, admin: AdminUser, session: Session, transport: Transport
) -> Added:
    try:
        isbn13 = isbn.normalise(body.isbn)
    except isbn.InvalidIsbn as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    # Checked before asking Open Library, so a book already here costs no request.
    existing = await session.scalar(select(Edition.work_id).where(Edition.isbn13 == isbn13))
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "That edition is already in the catalog.", "work_id": str(existing)},
        )
    try:
        found = await openlibrary.find_by_isbn(isbn13, transport)
    except openlibrary.NotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Open Library has no book with that ISBN."
        ) from None
    except openlibrary.Unavailable as exc:
        log.warning("Open Library lookup failed for %s: %s", isbn13, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Open Library didn't answer. Try again in a minute."
        ) from None

    try:
        work_id = await add_book(session, found)
    except AlreadyIndexed as exc:
        # Same edition under another ISBN, matched by Open Library's edition ID.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "That edition is already in the catalog.", "work_id": str(exc.work_id)},
        ) from None
    await session.commit()
    log.info("%s added %s (%s)", admin.id, isbn13, found.title)
    return Added(id=work_id)
