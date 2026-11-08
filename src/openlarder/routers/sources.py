"""Sources: the list, one source, adding a book by ISBN, and linking one to
Open Library.

Books are the only kind of source so far (migration 0019); the routes say
source because later kinds come through them too. Reading is public, because
the catalog is open data. Adding is for admins
until review exists (migration 0010); it looks the ISBN up on Open Library
and stores what comes back.
"""

import logging
import uuid
from collections.abc import Awaitable, Sequence
from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, select

from openlarder import books as books_module
from openlarder import isbn, linking, openlibrary, references, refresh
from openlarder.auth import AdminUser, SameOrigin
from openlarder.books import AlreadyIndexed, add_book
from openlarder.db import Session
from openlarder.models import (
    Author,
    Edition,
    Ingredient,
    IngredientOption,
    Recipe,
    RecipeLocation,
    Source,
    SourceCredit,
)
from openlarder.routers.ingredients import contains_pattern

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sources", tags=["sources"])


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
    # One per edition it is in, newest edition first; None = page not recorded.
    pages: list[str | None]


class TopIngredient(BaseModel):
    id: uuid.UUID
    name: str
    # Recipes in this book that use it.
    recipes: int


class Book(BaseModel):
    id: uuid.UUID
    title: str
    subtitle: str | None
    open_library_url: str | None
    credits: list[Credit]
    editions: list[EditionOut]
    recipes: list[RecipeSummary]
    # The ingredients its recipes use most, for finding your way in by one.
    ingredients: list[TopIngredient]


TOP_INGREDIENTS = 30


class AddByIsbn(BaseModel):
    isbn: str


class Added(BaseModel):
    id: uuid.UUID


def _cover(cover_id: int | None) -> str | None:
    return openlibrary.cover_url(cover_id) if cover_id else None


@router.get("", response_model=list[BookSummary])
async def list_books(
    session: Session,
    q: str = Query("", max_length=200),
    limit: int | None = Query(None, ge=1, le=50),
) -> list[BookSummary]:
    """Every book, by title; or, with q, those with every word of it in the
    title, subtitle or a credited name, ignoring case. limit is for pickers,
    which show a handful as someone types."""
    query = select(Source).order_by(func.lower(Source.title), Source.id)
    for word in q.casefold().split()[:10]:
        like = contains_pattern(word)
        query = query.where(
            Source.title.ilike(like, escape="\\")
            | Source.subtitle.ilike(like, escape="\\")
            | exists().where(
                SourceCredit.source_id == Source.id,
                SourceCredit.credited_as.ilike(like, escape="\\"),
            )
        )
    if limit:
        query = query.limit(limit)
    return await summaries(session, (await session.scalars(query)).all())


async def summaries(session: Session, works: Sequence[Source]) -> list[BookSummary]:
    """Books as cards, in the order given: credits, a cover, how many
    editions."""
    if not works:
        return []
    ids = [w.id for w in works]
    credits = (
        await session.execute(
            select(SourceCredit.source_id, SourceCredit.credited_as)
            .where(SourceCredit.source_id.in_(ids))
            .order_by(SourceCredit.source_id, SourceCredit.position)
        )
    ).all()
    editions = (
        await session.execute(
            select(Edition.source_id, Edition.open_library_cover_id)
            .where(Edition.source_id.in_(ids))
            .order_by(Edition.source_id, Edition.published_year.desc().nulls_last())
        )
    ).all()
    names: dict[uuid.UUID, list[str]] = {}
    for source_id, name in credits:
        names.setdefault(source_id, []).append(name)
    covers: dict[uuid.UUID, int | None] = {}
    counts: dict[uuid.UUID, int] = {}
    for source_id, cover_id in editions:
        counts[source_id] = counts.get(source_id, 0) + 1
        # The newest edition with a cover stands for the book.
        if covers.get(source_id) is None:
            covers[source_id] = cover_id
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


@router.get("/{source_id}", response_model=Book)
async def get_book(source_id: uuid.UUID, session: Session) -> Book:
    work = await session.get(Source, source_id)
    if work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    credits = (
        await session.execute(
            select(SourceCredit, Author.id)
            .join(Author, Author.id == SourceCredit.author_id)
            .where(SourceCredit.source_id == source_id)
            .order_by(SourceCredit.position)
        )
    ).all()
    editions = (
        await session.scalars(
            select(Edition)
            .where(Edition.source_id == source_id)
            .order_by(Edition.published_year.desc().nulls_last(), Edition.isbn13)
        )
    ).all()
    recipes = (
        await session.scalars(
            select(Recipe).where(Recipe.source_id == source_id).order_by(func.lower(Recipe.title))
        )
    ).all()
    edition_order = {e.id: i for i, e in enumerate(editions)}
    pages: dict[uuid.UUID, list[tuple[int, str | None]]] = {}
    for recipe_id, edition_id, page in (
        await session.execute(
            select(RecipeLocation.recipe_id, RecipeLocation.edition_id, RecipeLocation.page).where(
                RecipeLocation.source_id == source_id
            )
        )
    ).all():
        pages.setdefault(recipe_id, []).append((edition_order.get(edition_id, 0), page))
    uses = func.count(func.distinct(IngredientOption.recipe_id))
    top = await session.execute(
        select(Ingredient.id, Ingredient.name, uses)
        .join(IngredientOption, IngredientOption.ingredient_id == Ingredient.id)
        .join(Recipe, Recipe.id == IngredientOption.recipe_id)
        .where(Recipe.source_id == source_id)
        .group_by(Ingredient.id, Ingredient.name)
        .order_by(uses.desc(), func.lower(Ingredient.name))
        .limit(TOP_INGREDIENTS)
    )
    return Book(
        id=work.id,
        title=work.title,
        subtitle=work.subtitle,
        open_library_url=(
            openlibrary.work_url(work.open_library_work_id) if work.open_library_work_id else None
        ),
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
        recipes=[
            RecipeSummary(id=r.id, title=r.title, pages=[p for _, p in sorted(pages.get(r.id, []))])
            for r in recipes
        ],
        ingredients=[TopIngredient(id=i, name=n, recipes=c) for i, n, c in top],
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
    existing = await session.scalar(select(Edition.source_id).where(Edition.isbn13 == isbn13))
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "That edition is already in the catalog.", "source_id": str(existing)},
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
        source_id = await add_book(session, found)
    except AlreadyIndexed as exc:
        # Same edition under another ISBN, matched by Open Library's edition ID.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "That edition is already in the catalog.", "source_id": str(exc.source_id)},
        ) from None
    await session.commit()
    log.info("%s added %s (%s)", admin.id, isbn13, found.title)
    return Added(id=source_id)


class WithoutIsbn(BaseModel):
    title: str
    authors: list[str] = []
    year: int | None = None
    # For a book Open Library doesn't know, which still has an ISBN.
    isbn: str | None = None


class AddedManually(BaseModel):
    id: uuid.UUID
    existing: bool


@router.post("/manual", response_model=AddedManually, dependencies=[SameOrigin])
async def add_without_isbn(body: WithoutIsbn, admin: AdminUser, session: Session) -> AddedManually:
    """A book Open Library can't supply: no ISBN, or one Open Library doesn't know."""
    title = " ".join(body.title.split())
    authors = [a for a in (" ".join(x.split()) for x in body.authors) if a]
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the book its title.")
    if body.year is not None and not 1400 <= body.year <= 2200:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That year can't be right.")
    try:
        isbn13 = isbn.normalise(body.isbn) if body.isbn and body.isbn.strip() else None
    except isbn.InvalidIsbn as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    source_id, existed = await books_module.add_without_isbn(
        session, title, authors, body.year, isbn13
    )
    await session.commit()
    if not existed:
        log.info("%s added %s without an ISBN", admin.id, title)
    return AddedManually(id=source_id, existing=existed)


class LinkIn(BaseModel):
    reference: str


class LinkAuthor(BaseModel):
    name: str
    open_library_url: str
    outcome: str  # linked | link | add | unmatched; see linking.AuthorStep
    credited_as: str | None


class LinkEdition(BaseModel):
    title: str | None
    isbn13: str | None
    publisher: str | None
    published_year: int | None
    cover_url: str | None
    open_library_url: str
    # "fill" when it is this book's edition, with its blanks filled; "add"
    # when it becomes another edition.
    step: str
    fills_isbn13: str | None


class LinkPreview(BaseModel):
    open_library_url: str | None
    title: str
    subtitle: str | None
    edition: LinkEdition | None
    authors: list[LinkAuthor]
    # Why it can't be linked; nothing is linked while there is one.
    problem: str | None


async def _plan(
    source_id: uuid.UUID, body: LinkIn, session: Session, transport: Transport
) -> tuple[Source, linking.Plan]:
    work = await session.get(Source, source_id)
    if work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    try:
        reference = openlibrary.parse_reference(body.reference)
    except openlibrary.BadReference as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    try:
        found = await openlibrary.find(reference, transport)
    except openlibrary.NotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Open Library has nothing under that."
        ) from None
    except openlibrary.Unavailable as exc:
        log.warning("Open Library lookup failed for %s: %s", reference, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Open Library didn't answer. Try again in a minute."
        ) from None
    return work, await linking.plan(session, work, found)


@router.post(
    "/{source_id}/open-library/preview", response_model=LinkPreview, dependencies=[SameOrigin]
)
async def preview_link(
    source_id: uuid.UUID, body: LinkIn, admin: AdminUser, session: Session, transport: Transport
) -> LinkPreview:
    """What linking would do, for the admin to check it's the same book."""
    _, plan = await _plan(source_id, body, session, transport)
    found = plan.found
    return LinkPreview(
        open_library_url=openlibrary.work_url(found.open_library_work_id)
        if found.open_library_work_id
        else None,
        title=found.title,
        subtitle=found.subtitle,
        edition=(
            LinkEdition(
                title=found.edition_title,
                isbn13=found.isbn13,
                publisher=found.publisher,
                published_year=found.published_year,
                cover_url=_cover(found.cover_id),
                open_library_url=openlibrary.book_url(found.edition_id),
                step=plan.edition_step,
                fills_isbn13=plan.edition.isbn13 if plan.edition else None,
            )
            if found.edition_id and plan.edition_step
            else None
        ),
        authors=[
            LinkAuthor(
                name=step.found.name,
                open_library_url=openlibrary.author_url(step.found.open_library_id),
                outcome=step.outcome,
                credited_as=step.credit.credited_as if step.credit else None,
            )
            for step in plan.authors
        ],
        problem=plan.problem,
    )


@router.post("/{source_id}/open-library", response_model=Added, dependencies=[SameOrigin])
async def link(
    source_id: uuid.UUID, body: LinkIn, admin: AdminUser, session: Session, transport: Transport
) -> Added:
    """Link the book, looking the record up again rather than trusting the preview's."""
    work, plan = await _plan(source_id, body, session, transport)
    if plan.problem:
        raise HTTPException(status.HTTP_409_CONFLICT, plan.problem)
    await linking.apply(session, work, plan)
    await session.commit()
    log.info("%s linked %s to Open Library %s", admin.id, work.id, plan.found.open_library_work_id)
    return Added(id=work.id)


class Relinked(BaseModel):
    # Options in the book now linked to the recipe they cite.
    linked: int


@router.post("/{source_id}/references", response_model=Relinked, dependencies=[SameOrigin])
async def relink_references(source_id: uuid.UUID, admin: AdminUser, session: Session) -> Relinked:
    """Link a book's page references again: for recipes stored before linking
    existed, which the Admin page runs over every book."""
    if await session.get(Source, source_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    await references.relink(session, source_id)
    await session.commit()
    linked = await session.scalar(
        select(func.count())
        .select_from(IngredientOption)
        .join(Recipe, Recipe.id == IngredientOption.recipe_id)
        .where(Recipe.source_id == source_id, IngredientOption.sub_recipe_id.is_not(None))
    )
    return Relinked(linked=linked or 0)


class CreditIn(BaseModel):
    # An author already credited on the book, or none for a new name.
    author_id: uuid.UUID | None = None
    name: str = Field(max_length=200)
    role: str = "author"


class EditionIn(BaseModel):
    id: uuid.UUID
    title: str | None = Field(default=None, max_length=300)
    publisher: str | None = Field(default=None, max_length=200)
    published_year: int | None = None


class BookIn(BaseModel):
    title: str = Field(max_length=300)
    subtitle: str | None = Field(default=None, max_length=500)
    credits: list[CreditIn] = Field(default=[], max_length=30)
    # Editions left out are left as they are.
    editions: list[EditionIn] = []


@router.put("/{source_id}", response_model=Added, dependencies=[SameOrigin])
async def edit_book(
    source_id: uuid.UUID, body: BookIn, admin: AdminUser, session: Session
) -> Added:
    """Fix what a book says about itself (books.edit_book)."""
    work = await session.get(Source, source_id)
    if work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    try:
        await books_module.edit_book(
            session,
            work,
            body.title,
            body.subtitle,
            [books_module.CreditEdit(c.author_id, c.name, c.role) for c in body.credits],
            [
                books_module.EditionEdit(e.id, e.title, e.publisher, e.published_year)
                for e in body.editions
            ],
        )
    except books_module.InvalidBook as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await session.commit()
    log.info("%s edited book %s", admin.id, source_id)
    return Added(id=work.id)


class DifferenceOut(BaseModel):
    key: str
    label: str
    ours: str | None
    theirs: str | None
    # ours and theirs are cover image addresses.
    cover: bool


class Checked(BaseModel):
    open_library_url: str
    differences: list[DifferenceOut]


class TakeIn(BaseModel):
    keys: list[str] = Field(max_length=200)


class Taken(BaseModel):
    taken: int
    # What still differs afterwards.
    differences: list[DifferenceOut]


async def _open_library[T](work: Source, call: Awaitable[T]) -> T:
    """A call to Open Library, with its failures as HTTP answers."""
    try:
        return await call
    except refresh.NotLinked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except openlibrary.NotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Open Library no longer has this book's record."
        ) from None
    except openlibrary.Unavailable as exc:
        log.warning("Open Library check failed for %s: %s", work.id, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Open Library didn't answer. Try again in a minute."
        ) from None


def _out(differences: list[refresh.Difference]) -> list[DifferenceOut]:
    return [
        DifferenceOut(key=d.key, label=d.label, ours=d.ours, theirs=d.theirs, cover=d.cover)
        for d in differences
    ]


@router.post("/{source_id}/open-library/check", response_model=Checked, dependencies=[SameOrigin])
async def check_open_library(
    source_id: uuid.UUID, admin: AdminUser, session: Session, transport: Transport
) -> Checked:
    """What differs between the book as stored and Open Library now. Changes
    nothing (refresh.py)."""
    work = await session.get(Source, source_id)
    if work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    differences = await _open_library(work, refresh.check(session, work, transport))
    assert work.open_library_work_id is not None
    return Checked(
        open_library_url=openlibrary.work_url(work.open_library_work_id),
        differences=_out(differences),
    )


@router.post("/{source_id}/open-library/take", response_model=Taken, dependencies=[SameOrigin])
async def take_from_open_library(
    source_id: uuid.UUID, body: TakeIn, admin: AdminUser, session: Session, transport: Transport
) -> Taken:
    """Take the ticked differences from Open Library, fetched again now."""
    work = await session.get(Source, source_id)
    if work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    taken = await _open_library(work, refresh.apply(session, work, set(body.keys), transport))
    await session.commit()
    log.info("%s took %d changes from Open Library for %s", admin.id, taken, source_id)
    left = await _open_library(work, refresh.check(session, work, transport))
    return Taken(taken=taken, differences=_out(left))
