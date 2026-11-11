"""Author pages: the authors list, one author's books, co-authors and links,
and fixing an author (admins).

Reading is public, like the rest of the catalog. A page shows the author's
books, linking to each, and the people credited with them on those books;
their links; Open Library, where the record came from; and facts from
Wikidata (author_facts.py): born and died, country, website. Bios and photos
come later (SCOPING, "Author pages"; TODO.md).

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
from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased

from openlarder import author_facts, author_merge, openlibrary, visibility, wikidata
from openlarder.auth import ModeratorUser, SameOrigin, Viewer
from openlarder.db import Session
from openlarder.models import Author, AuthorLink, Recipe, Source, SourceCredit
from openlarder.routers.ingredients import contains_pattern
from openlarder.routers.sources import BookSummary, summaries
from openlarder.wikidata import WikidataTransport, wikidata_transport  # noqa: F401

router = APIRouter(prefix="/api/authors", tags=["authors"])

PAGE = 100


class KnownFor(BaseModel):
    id: uuid.UUID
    title: str


class AuthorSummary(BaseModel):
    id: uuid.UUID
    name: str
    sources: int


class AuthorListed(AuthorSummary):
    # For the Authors page: a person or an organisation, how many recipes
    # their sources hold, and the one of them with the most.
    kind: str
    recipes: int
    known_for: KnownFor | None


class AuthorList(BaseModel):
    authors: list[AuthorListed]
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
    sources: int


class AuthorOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: Literal["person", "organisation"]
    open_library_url: str | None
    # From Wikidata, when the author is on it.
    wikidata_url: str | None
    born_year: int | None
    died_year: int | None
    country: str | None
    website: str | None
    links: list[LinkOut]
    sources: list[AuthorBook]
    coauthors: list[CoAuthor]
    # Other authors whose names compare the same: likely the same person,
    # to merge (author_merge.py).
    same_name: list[AuthorSummary]


@router.get("", response_model=AuthorList)
async def list_authors(
    session: Session,
    viewer: Viewer,
    q: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    # "name": A to Z; "recipes": the most recipes first.
    sort: Literal["name", "recipes"] = "name",
    # Only people, or only organisations (a test kitchen, a magazine's staff).
    kind: Literal["person", "organisation"] | None = None,
) -> AuthorList:
    """Authors by name, with how many books credit them; with q, those with
    every word of it in their name or a name a book prints for them."""
    books = func.count(func.distinct(SourceCredit.source_id))
    # The recipes in the sources crediting them that the viewer can see;
    # aliased, so it doesn't take the outer query's credits for its own.
    credit = aliased(SourceCredit)
    recipes = (
        # Distinct: someone credited twice on a book (author and photographer)
        # is still credited with its recipes once.
        select(func.count(func.distinct(Recipe.id)))
        .join(credit, credit.source_id == Recipe.source_id)
        .where(
            credit.author_id == Author.id,
            visibility.recipes_seen_by(viewer),
        )
        .scalar_subquery()
    )
    query = (
        select(Author.id, Author.name, books, Author.kind, recipes.label("recipes"))
        .join(SourceCredit, SourceCredit.author_id == Author.id)
        .where(SourceCredit.source_id.in_(visibility.seen_source_ids(viewer)))
        .group_by(Author.id, Author.name, Author.kind)
    )
    if kind:
        query = query.where(Author.kind == kind)
    for word in q.casefold().split()[:10]:
        like = contains_pattern(word)
        query = query.having(
            func.bool_or(
                Author.name.ilike(like, escape="\\")
                | SourceCredit.credited_as.ilike(like, escape="\\")
            )
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    order = (
        (recipes.desc(), func.lower(Author.name), Author.id)
        if sort == "recipes"
        else (func.lower(Author.name), Author.id)
    )
    rows = (await session.execute(query.order_by(*order).offset(offset).limit(PAGE))).all()
    # Each one's source with the most recipes, of those the viewer can see.
    known: dict[uuid.UUID, tuple[int, KnownFor]] = {}
    count = func.count(Recipe.id)
    for author_id, source_id, title, n in await session.execute(
        select(SourceCredit.author_id, Source.id, Source.title, count)
        .join(Source, Source.id == SourceCredit.source_id)
        .outerjoin(Recipe, and_(Recipe.source_id == Source.id, visibility.recipes_seen_by(viewer)))
        .where(
            SourceCredit.author_id.in_([r[0] for r in rows]),
            Source.id.in_(visibility.seen_source_ids(viewer)),
        )
        .group_by(SourceCredit.author_id, Source.id, Source.title)
        .order_by(SourceCredit.author_id, count.desc(), func.lower(Source.title))
    ):
        known.setdefault(author_id, (n, KnownFor(id=source_id, title=title)))
    return AuthorList(
        authors=[
            AuthorListed(
                id=i,
                name=n,
                sources=c,
                kind=k,
                recipes=r or 0,
                known_for=known[i][1] if i in known else None,
            )
            for i, n, c, k, r in rows
        ],
        total=total or 0,
    )


async def _author_or_404(session: Session, author_id: uuid.UUID) -> Author:
    author = await session.get(Author, author_id)
    if author is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such author.")
    return author


@router.get("/{author_id}", response_model=AuthorOut)
async def get_author(author_id: uuid.UUID, session: Session, viewer: Viewer) -> AuthorOut:
    author = await session.scalar(
        select(Author).where(Author.id == author_id, visibility.authors_seen_by(viewer))
    )
    if author is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such author.")
    seen = visibility.seen_source_ids(viewer)
    credits = (
        await session.execute(
            select(SourceCredit.source_id, SourceCredit.role, SourceCredit.credited_as)
            .where(SourceCredit.author_id == author_id, SourceCredit.source_id.in_(seen))
            .order_by(SourceCredit.position)
        )
    ).all()
    roles: dict[uuid.UUID, list[str]] = {}
    printed: dict[uuid.UUID, str] = {}
    for source_id, role, credited_as in credits:
        roles.setdefault(source_id, []).append(role)
        printed.setdefault(source_id, credited_as)
    works = (
        await session.scalars(
            select(Source).where(Source.id.in_(roles)).order_by(func.lower(Source.title), Source.id)
        )
    ).all()
    books = [
        AuthorBook(**card.model_dump(), roles=roles[card.id], credited_as=printed[card.id])
        for card in await summaries(session, works)
    ]
    shared = func.count(func.distinct(SourceCredit.source_id))
    coauthors = await session.execute(
        select(Author.id, Author.name, shared)
        .join(SourceCredit, SourceCredit.author_id == Author.id)
        .where(SourceCredit.source_id.in_(roles), Author.id != author_id)
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
        wikidata_url=wikidata.item_url(author.wikidata_id) if author.wikidata_id else None,
        born_year=author.born_year,
        died_year=author.died_year,
        country=author.country,
        website=author.website,
        links=[LinkOut(id=x.id, url=x.url, label=x.label) for x in links],
        sources=books,
        coauthors=[CoAuthor(id=i, name=n, sources=c) for i, n, c in coauthors],
        same_name=[
            AuthorSummary(id=i, name=n, sources=c)
            for i, n, c in await session.execute(
                select(Author.id, Author.name, func.count(func.distinct(SourceCredit.source_id)))
                .outerjoin(
                    SourceCredit,
                    (SourceCredit.author_id == Author.id) & SourceCredit.source_id.in_(seen),
                )
                .where(
                    Author.name_key == author.name_key,
                    Author.id != author.id,
                    visibility.authors_seen_by(viewer),
                )
                .group_by(Author.id, Author.name)
                .order_by(func.lower(Author.name), Author.id)
            )
        ],
    )


# Fixing an author


class AuthorIn(BaseModel):
    name: str = Field(max_length=200)
    kind: Literal["person", "organisation"]


@router.patch("/{author_id}", response_model=AuthorSummary, dependencies=[SameOrigin])
async def edit_author(
    author_id: uuid.UUID, body: AuthorIn, admin: ModeratorUser, session: Session
) -> AuthorSummary:
    author = await _author_or_404(session, author_id)
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the author a name.")
    author.name = name
    author.kind = body.kind
    await session.commit()
    books = await session.scalar(
        select(func.count(func.distinct(SourceCredit.source_id))).where(
            SourceCredit.author_id == author_id
        )
    )
    return AuthorSummary(id=author.id, name=author.name, sources=books or 0)


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
    author_id: uuid.UUID, body: LinkIn, admin: ModeratorUser, session: Session
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
    author_id: uuid.UUID, link_id: uuid.UUID, admin: ModeratorUser, session: Session
) -> Response:
    link = await session.get(AuthorLink, link_id)
    if link is None or link.author_id != author_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such link for this author.")
    await session.delete(link)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class MergeInto(BaseModel):
    into: uuid.UUID


@router.post("/{author_id}/merge", response_model=AuthorSummary, dependencies=[SameOrigin])
async def merge_author(
    author_id: uuid.UUID, body: MergeInto, admin: ModeratorUser, session: Session
) -> AuthorSummary:
    """Merge this author into another; answers with the one that's left."""
    gone = await _author_or_404(session, author_id)
    kept = await _author_or_404(session, body.into)
    try:
        await author_merge.merge(session, gone, kept)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await session.commit()
    sources = await session.scalar(
        select(func.count(func.distinct(SourceCredit.source_id))).where(
            SourceCredit.author_id == kept.id
        )
    )
    return AuthorSummary(id=kept.id, name=kept.name, sources=sources or 0)


# Facts from Wikidata


class ClashOut(BaseModel):
    author: AuthorSummary
    other: AuthorSummary


class WikidataRun(BaseModel):
    checked: int
    found: int
    # Authors whose item another author has: probably one person twice.
    clashes: list[ClashOut]
    # Still to ask about after this batch.
    remaining: int


def _unavailable(exc: wikidata.Unavailable) -> HTTPException:
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY, f"Wikidata didn't answer. Try again later. ({exc})"
    )


@router.post("/wikidata", response_model=WikidataRun, dependencies=[SameOrigin])
async def check_wikidata(
    admin: ModeratorUser, session: Session, transport: WikidataTransport
) -> WikidataRun:
    """Ask Wikidata about the next batch of authors not asked lately; the
    admin page calls this until none remain."""
    batch = list(
        await session.scalars(
            author_facts.due()
            .order_by(Author.wikidata_checked_at.nulls_first(), Author.id)
            .limit(author_facts.BATCH)
            .with_for_update(skip_locked=True)
        )
    )
    try:
        done = await author_facts.check(session, batch, transport)
    except wikidata.Unavailable as exc:
        raise _unavailable(exc) from None
    await session.commit()
    remaining = await session.scalar(
        select(func.count()).select_from(author_facts.due().subquery())
    )
    return WikidataRun(
        checked=done.checked,
        found=done.found,
        clashes=[
            ClashOut(
                author=AuthorSummary(id=c.author_id, name=c.name, sources=0),
                other=AuthorSummary(id=c.other_id, name=c.other_name, sources=0),
            )
            for c in done.clashes
        ],
        remaining=remaining or 0,
    )


class WikidataIn(BaseModel):
    # A Wikidata ID or a link to the item; null takes it off.
    reference: str | None = Field(default=None, max_length=300)


@router.put("/{author_id}/wikidata", response_model=AuthorOut, dependencies=[SameOrigin])
async def set_wikidata(
    author_id: uuid.UUID,
    body: WikidataIn,
    admin: ModeratorUser,
    session: Session,
    transport: WikidataTransport,
) -> AuthorOut:
    """Say which Wikidata item the author is, and fetch its facts; or take
    it off, with its facts."""
    author = await _author_or_404(session, author_id)
    if not (body.reference or "").strip():
        author.wikidata_id = None
        author.born_year = author.died_year = author.country = author.website = None
        author.wikidata_checked_at = None
    else:
        try:
            item = wikidata.parse_reference(body.reference or "")
        except wikidata.BadReference as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        other = await session.scalar(
            select(Author).where(Author.wikidata_id == item, Author.id != author_id)
        )
        if other is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "message": f"{other.name} is that Wikidata item already. Merge them instead.",
                    "author": {"id": str(other.id), "name": other.name},
                },
            )
        author.wikidata_id = item
        try:
            done = await author_facts.check(session, [author], transport)
        except wikidata.Unavailable as exc:
            raise _unavailable(exc) from None
        if not done.found:
            await session.rollback()
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Wikidata has no item {item}."
            )
    await session.commit()
    return await get_author(author_id, session, admin)
