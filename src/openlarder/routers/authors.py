"""Author pages: the authors list, one author's books, co-authors and links,
and fixing an author (admins).

Reading is public, like the rest of the catalog. A page shows the author's
books, linking to each, and the people credited with them on those books;
their links; and Open Library, where the record came from. Wikidata facts,
bios and photos come later (SCOPING, "Author pages"; TODO.md).

An admin can fix the author's own name and kind here, Open Library authors
included: Open Library's names come as it files them ("Moore, Russell
(Chef)", "America's Test Kitchen (Firm)"), and this is where the record
itself is fixed. Editing a book changes only how that book prints the name.
"""

import uuid
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from openlarder import openlibrary
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import Author, AuthorLink, Work, WorkCredit
from openlarder.routers.books import BookSummary, summaries
from openlarder.routers.ingredients import contains_pattern

router = APIRouter(prefix="/api/authors", tags=["authors"])

PAGE = 100


class AuthorSummary(BaseModel):
    id: uuid.UUID
    name: str
    books: int


class AuthorList(BaseModel):
    authors: list[AuthorSummary]
    total: int


class LinkOut(BaseModel):
    id: uuid.UUID
    url: str
    label: str | None


class AuthorBook(BookSummary):
    # This author's roles on it, and the name it prints for them.
    roles: list[str]
    credited_as: str


class CoAuthor(BaseModel):
    id: uuid.UUID
    name: str
    # Books they share with this author.
    books: int


class AuthorOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: Literal["person", "organisation"]
    open_library_url: str | None
    links: list[LinkOut]
    books: list[AuthorBook]
    coauthors: list[CoAuthor]


@router.get("", response_model=AuthorList)
async def list_authors(
    session: Session, q: str = Query("", max_length=200), offset: int = Query(0, ge=0)
) -> AuthorList:
    """Authors by name, with how many books credit them; with q, those with
    every word of it in their name or a name a book prints for them."""
    books = func.count(func.distinct(WorkCredit.work_id))
    query = (
        select(Author.id, Author.name, books)
        .join(WorkCredit, WorkCredit.author_id == Author.id)
        .group_by(Author.id, Author.name)
    )
    for word in q.casefold().split()[:10]:
        like = contains_pattern(word)
        query = query.having(
            func.bool_or(
                Author.name.ilike(like, escape="\\")
                | WorkCredit.credited_as.ilike(like, escape="\\")
            )
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(func.lower(Author.name), Author.id).offset(offset).limit(PAGE)
    )
    return AuthorList(
        authors=[AuthorSummary(id=i, name=n, books=c) for i, n, c in rows], total=total or 0
    )


async def _author_or_404(session: Session, author_id: uuid.UUID) -> Author:
    author = await session.get(Author, author_id)
    if author is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such author.")
    return author


@router.get("/{author_id}", response_model=AuthorOut)
async def get_author(author_id: uuid.UUID, session: Session) -> AuthorOut:
    author = await _author_or_404(session, author_id)
    credits = (
        await session.execute(
            select(WorkCredit.work_id, WorkCredit.role, WorkCredit.credited_as)
            .where(WorkCredit.author_id == author_id)
            .order_by(WorkCredit.position)
        )
    ).all()
    roles: dict[uuid.UUID, list[str]] = {}
    printed: dict[uuid.UUID, str] = {}
    for work_id, role, credited_as in credits:
        roles.setdefault(work_id, []).append(role)
        printed.setdefault(work_id, credited_as)
    works = (
        await session.scalars(
            select(Work).where(Work.id.in_(roles)).order_by(func.lower(Work.title), Work.id)
        )
    ).all()
    books = [
        AuthorBook(**card.model_dump(), roles=roles[card.id], credited_as=printed[card.id])
        for card in await summaries(session, works)
    ]
    shared = func.count(func.distinct(WorkCredit.work_id))
    coauthors = await session.execute(
        select(Author.id, Author.name, shared)
        .join(WorkCredit, WorkCredit.author_id == Author.id)
        .where(WorkCredit.work_id.in_(roles), Author.id != author_id)
        .group_by(Author.id, Author.name)
        .order_by(shared.desc(), func.lower(Author.name))
    )
    links = await session.scalars(
        select(AuthorLink)
        .where(AuthorLink.author_id == author_id)
        .order_by(func.lower(func.coalesce(AuthorLink.label, AuthorLink.url)))
    )
    return AuthorOut(
        id=author.id,
        name=author.name,
        kind=author.kind,
        open_library_url=(
            openlibrary.author_url(author.open_library_author_id)
            if author.open_library_author_id
            else None
        ),
        links=[LinkOut(id=x.id, url=x.url, label=x.label) for x in links],
        books=books,
        coauthors=[CoAuthor(id=i, name=n, books=c) for i, n, c in coauthors],
    )


# Fixing an author


class AuthorIn(BaseModel):
    name: str = Field(max_length=200)
    kind: Literal["person", "organisation"]


@router.patch("/{author_id}", response_model=AuthorSummary, dependencies=[SameOrigin])
async def edit_author(
    author_id: uuid.UUID, body: AuthorIn, admin: AdminUser, session: Session
) -> AuthorSummary:
    author = await _author_or_404(session, author_id)
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the author a name.")
    author.name = name
    author.kind = body.kind
    await session.commit()
    books = await session.scalar(
        select(func.count(func.distinct(WorkCredit.work_id))).where(
            WorkCredit.author_id == author_id
        )
    )
    return AuthorSummary(id=author.id, name=author.name, books=books or 0)


class LinkIn(BaseModel):
    url: str = Field(max_length=500)
    label: str | None = Field(default=None, max_length=100)


@router.post(
    "/{author_id}/links",
    response_model=LinkOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def add_link(
    author_id: uuid.UUID, body: LinkIn, admin: AdminUser, session: Session
) -> LinkOut:
    """The author's own website or account. Only http and https, so a link
    can't run script on the page that shows it."""
    await _author_or_404(session, author_id)
    url = body.url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A link is a web address starting http:// or https://.",
        )
    taken = await session.scalar(
        select(AuthorLink.id).where(AuthorLink.author_id == author_id, AuthorLink.url == url)
    )
    if taken is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That link is here already.")
    link = AuthorLink(
        author_id=author_id, url=url, label=" ".join((body.label or "").split()) or None
    )
    session.add(link)
    await session.commit()
    return LinkOut(id=link.id, url=link.url, label=link.label)


@router.delete(
    "/{author_id}/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SameOrigin],
)
async def remove_link(
    author_id: uuid.UUID, link_id: uuid.UUID, admin: AdminUser, session: Session
) -> Response:
    link = await session.get(AuthorLink, link_id)
    if link is None or link.author_id != author_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such link for this author.")
    await session.delete(link)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
