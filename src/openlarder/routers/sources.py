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
from datetime import date
from typing import Annotated, Literal

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, exists, func, select

from openlarder import (
    book_merge,
    buying,
    history,
    isbn,
    linking,
    openlibrary,
    references,
    refresh,
    visibility,
    web,
)
from openlarder import books as books_module
from openlarder import recipes as recipes_module
from openlarder.agreement import Agreed, Contributing, require_agreement
from openlarder.auth import CurrentUser, ModeratorUser, SameOrigin, Viewer
from openlarder.books import AlreadyIndexed, add_book
from openlarder.buying import BuyLink
from openlarder.db import Session
from openlarder.models import (
    Author,
    Edition,
    Episode,
    Group,
    GroupMember,
    Ingredient,
    IngredientOption,
    Issue,
    Recipe,
    RecipeIngredient,
    RecipeLocation,
    Source,
    SourceCredit,
    SourceGroup,
    User,
)
from openlarder.routers.ingredients import contains_pattern
from openlarder.tagging import TagOut, source_tags

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sources", tags=["sources"])


def openlibrary_transport() -> httpx2.AsyncBaseTransport | None:
    """None means the real Open Library; tests replace this with a fake."""
    return None


Transport = Annotated[httpx2.AsyncBaseTransport | None, Depends(openlibrary_transport)]


class BookSummary(BaseModel):
    id: uuid.UUID
    # "book" or "website"; a website's host, as "smittenkitchen.com".
    kind: str
    host: str | None
    title: str
    subtitle: str | None
    authors: list[str]
    cover_url: str | None
    editions: int
    recipes: int = 0
    # A family collection only its owner sees.
    private: bool = False


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
    # Where to buy it, through /go/; none until an affiliate ID is set.
    buy: list[BuyLink] = []


class PlaceSummary(BaseModel):
    edition_id: uuid.UUID
    page: str | None


# Ingredient lines a recipe list shows before "+N".
FIRST_LINES = 3


class RecipeSummary(BaseModel):
    id: uuid.UUID
    title: str
    chapter: str | None = None
    # One per edition it is in, newest edition first; None = page not recorded.
    # A magazine's or newspaper's: its page in its issue.
    pages: list[str | None]
    # A magazine's or newspaper's recipe: the issue it's in.
    issue: str | None = None
    # A TV show's, podcast's or video channel's: the episode, and the time
    # in it.
    episode: str | None = None
    at: str | None = None
    # A book's recipe: its page in each edition it's in (None, not recorded).
    editions: list[PlaceSummary] = []
    # The first of its ingredient lines as written, and how many there are.
    lines: list[str] = []
    line_count: int = 0
    # Another recipe here uses it as a component ("Biscuit Blend (p. 14)").
    component: bool = False
    # published, or (for its maker and moderators) pending or returned.
    review: str = "published"


class IssueSummary(BaseModel):
    id: uuid.UUID
    label: str
    published_on: date | None


class EpisodeSummary(BaseModel):
    id: uuid.UUID
    name: str
    season: int | None
    number: int | None
    title: str | None
    url: str | None
    aired_on: date | None


class GroupRef(BaseModel):
    id: uuid.UUID
    name: str


class TopIngredient(BaseModel):
    id: uuid.UUID
    name: str
    # Recipes in this book that use it.
    recipes: int


class Book(BaseModel):
    id: uuid.UUID
    kind: str
    # A website's host, and whether it's behind a subscription.
    host: str | None
    paywalled: bool
    # Its tags, which every recipe in it has too.
    tags: list[TagOut] = []
    title: str
    subtitle: str | None
    open_library_url: str | None
    credits: list[Credit]
    editions: list[EditionOut]
    recipes: list[RecipeSummary]
    # The ingredients its recipes use most, for finding your way in by one.
    ingredients: list[TopIngredient]
    # A magazine's or newspaper's issues, newest first.
    issues: list[IssueSummary]
    # A family collection only its owner sees; and whether the viewer may
    # add to and change this source.
    private: bool
    editable: bool
    # A family collection's: whose it is, whether the viewer may rename,
    # delete or share it, and the groups it's shared with (all of them for
    # its owner; for anyone else, the ones they're in).
    owner_name: str | None = None
    manageable: bool = False
    shared_with: list[GroupRef] = []
    # A TV show's, podcast's or video channel's episodes, in order.
    episodes: list[EpisodeSummary]
    # published, or (for its maker and moderators) pending or returned, with
    # the moderator's note; and whether the viewer may change its details.
    review: str = "published"
    review_note: str | None = None
    details_editable: bool = False
    # Whether the viewer may change its tags (routers/tags.py).
    tags_editable: bool = False


TOP_INGREDIENTS = 30


# Adding to the catalog is under the contributor agreement (agreement.py).
AGREED = [SameOrigin, Depends(require_agreement)]


class AddByIsbn(BaseModel):
    isbn: str


class Added(BaseModel):
    id: uuid.UUID


def _cover(cover_id: int | None) -> str | None:
    return openlibrary.cover_url(cover_id) if cover_id else None


class SourceList(BaseModel):
    sources: list[BookSummary]
    # How many match, however many this page holds.
    total: int
    # How many of each kind match the words, whichever kinds were asked
    # for, for the Sources page's filter.
    kinds: dict[str, int] = {}


SourceKind = Literal[
    "book",
    "website",
    "magazine",
    "newspaper",
    "tv_show",
    "podcast",
    "video_channel",
    "social",
    "packaging",
    "family",
]


PAGE = 100


@router.get("", response_model=SourceList)
async def list_books(
    session: Session,
    viewer: Viewer,
    q: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(PAGE, ge=1, le=PAGE),
    # "recent": newest added first, for the front page; "recipes": the most
    # recipes first; otherwise by title.
    sort: Literal["title", "recent", "recipes"] = "title",
    # Only these kinds; every kind when none are given.
    kind: Annotated[list[SourceKind] | None, Query()] = None,
) -> SourceList:
    """Sources by title, a page at a time; with q, those with every word of
    it in the title, subtitle, a credited name or a website's address,
    ignoring case. Pickers ask for a handful (limit) as someone types; the
    Sources page a hundred at a time, since the whole catalog won't fit
    one answer."""
    query = select(Source).where(visibility.sources_seen_by(viewer))
    for word in q.casefold().split()[:10]:
        like = contains_pattern(word)
        query = query.where(
            Source.title.ilike(like, escape="\\")
            | Source.subtitle.ilike(like, escape="\\")
            | Source.host.ilike(like, escape="\\")
            | exists().where(
                SourceCredit.source_id == Source.id,
                SourceCredit.credited_as.ilike(like, escape="\\"),
            )
        )
    counted = query.subquery()
    kinds = dict(
        (await session.execute(select(counted.c.kind, func.count()).group_by(counted.c.kind))).all()
    )
    if kind:
        query = query.where(Source.kind.in_(kind))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    recipe_count = (
        select(func.count())
        .where(Recipe.source_id == Source.id, Recipe.review == "published")
        .scalar_subquery()
    )
    order = {
        "recent": (Source.created_at.desc(), Source.id),
        "recipes": (recipe_count.desc(), func.lower(Source.title), Source.id),
        "title": (func.lower(Source.title), Source.id),
    }[sort]
    page = await session.scalars(query.order_by(*order).offset(offset).limit(limit))
    return SourceList(sources=await summaries(session, page.all()), total=total or 0, kinds=kinds)


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
    recipe_counts = dict(
        (
            await session.execute(
                select(Recipe.source_id, func.count())
                .where(Recipe.source_id.in_(ids), Recipe.review == "published")
                .group_by(Recipe.source_id)
            )
        ).all()
    )
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
            kind=w.kind,
            host=w.host,
            title=w.title,
            subtitle=w.subtitle,
            authors=names.get(w.id, []),
            cover_url=_cover(covers.get(w.id)),
            editions=counts.get(w.id, 0),
            recipes=recipe_counts.get(w.id, 0),
            private=w.private,
        )
        for w in works
    ]


@router.get("/{source_id}", response_model=Book)
async def get_book(source_id: uuid.UUID, session: Session, viewer: Viewer) -> Book:
    work = await session.get(Source, source_id)
    if work is None or not await visibility.can_see(session, viewer, work):
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
            select(Recipe)
            .where(Recipe.source_id == source_id, visibility.recipes_seen_by(viewer))
            .order_by(func.lower(Recipe.title))
        )
    ).all()
    edition_order = {e.id: i for i, e in enumerate(editions)}
    issues = (
        await session.scalars(
            select(Issue)
            .where(Issue.source_id == source_id)
            .order_by(Issue.published_on.desc().nulls_last(), func.lower(Issue.label))
        )
    ).all()
    issue_labels = {i.id: i.label for i in issues}
    issue_of: dict[uuid.UUID, str] = {}
    for recipe_id, issue_id in await session.execute(
        select(RecipeLocation.recipe_id, RecipeLocation.issue_id).where(
            RecipeLocation.source_id == source_id, RecipeLocation.issue_id.is_not(None)
        )
    ):
        issue_of[recipe_id] = issue_labels[issue_id]
    episodes = (
        await session.scalars(
            select(Episode)
            .where(Episode.source_id == source_id)
            .order_by(
                Episode.season.nulls_last(),
                Episode.number.nulls_last(),
                Episode.aired_on.nulls_last(),
                func.lower(Episode.title),
            )
        )
    ).all()
    episode_names = {
        e.id: recipes_module.episode_name(e.season, e.number, e.title) for e in episodes
    }
    episode_of: dict[uuid.UUID, tuple[str, str | None]] = {}
    for recipe_id, episode_id, at in await session.execute(
        select(
            RecipeLocation.recipe_id, RecipeLocation.episode_id, RecipeLocation.at_seconds
        ).where(RecipeLocation.source_id == source_id, RecipeLocation.episode_id.is_not(None))
    ):
        episode_of[recipe_id] = (
            episode_names[episode_id],
            recipes_module.clock(at) if at is not None else None,
        )
    pages: dict[uuid.UUID, list[tuple[int, str | None]]] = {}
    placed: dict[uuid.UUID, list[PlaceSummary]] = {}
    for recipe_id, edition_id, page in (
        await session.execute(
            select(RecipeLocation.recipe_id, RecipeLocation.edition_id, RecipeLocation.page).where(
                RecipeLocation.source_id == source_id
            )
        )
    ).all():
        pages.setdefault(recipe_id, []).append((edition_order.get(edition_id, 0), page))
        if edition_id is not None:
            placed.setdefault(recipe_id, []).append(PlaceSummary(edition_id=edition_id, page=page))
    lines: dict[uuid.UUID, list[str]] = {}
    for recipe_id, line in await session.execute(
        select(RecipeIngredient.recipe_id, RecipeIngredient.original_text)
        .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
        .where(Recipe.source_id == source_id, visibility.recipes_seen_by(viewer))
        .order_by(RecipeIngredient.recipe_id, RecipeIngredient.position)
    ):
        lines.setdefault(recipe_id, []).append(line)
    components = set(
        (
            await session.scalars(
                select(IngredientOption.sub_recipe_id)
                .join(Recipe, Recipe.id == IngredientOption.recipe_id)
                .where(Recipe.source_id == source_id, visibility.recipes_seen_by(viewer))
            )
        ).all()
    )
    uses = func.count(func.distinct(IngredientOption.recipe_id))
    top = await session.execute(
        select(Ingredient.id, Ingredient.name, uses)
        .join(IngredientOption, IngredientOption.ingredient_id == Ingredient.id)
        .join(Recipe, Recipe.id == IngredientOption.recipe_id)
        .where(Recipe.source_id == source_id, visibility.recipes_seen_by(viewer))
        .group_by(Ingredient.id, Ingredient.name)
        .order_by(uses.desc(), func.lower(Ingredient.name))
        .limit(TOP_INGREDIENTS)
    )
    return Book(
        id=work.id,
        kind=work.kind,
        host=work.host,
        paywalled=work.paywalled,
        private=work.private,
        editable=viewer is not None and await visibility.may_edit(session, viewer, work),
        review=work.review,
        review_note=work.review_note if work.review != "published" else None,
        details_editable=viewer is not None and _may_change_book(viewer, work),
        tags_editable=viewer is not None
        and await visibility.may_edit(session, viewer, work)
        and visibility.may_tag_source(viewer, work),
        owner_name=(
            (await session.get_one(User, work.owner_id)).display_name if work.owner_id else None
        ),
        manageable=viewer is not None and visibility.may_manage(viewer, work),
        shared_with=await _shared_with(session, work, viewer),
        title=work.title,
        subtitle=work.subtitle,
        tags=await source_tags(session, work.id),
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
                buy=buying.links(
                    e.id,
                    e.isbn13,
                    work.kind,
                    work.title,
                    credits[0][0].credited_as if credits else None,
                ),
            )
            for e in editions
        ],
        recipes=[
            RecipeSummary(
                id=r.id,
                title=r.title,
                chapter=r.chapter,
                pages=[p for _, p in sorted(pages.get(r.id, []))],
                issue=issue_of.get(r.id),
                episode=episode_of[r.id][0] if r.id in episode_of else None,
                at=episode_of[r.id][1] if r.id in episode_of else None,
                editions=placed.get(r.id, []),
                lines=lines.get(r.id, [])[:FIRST_LINES],
                line_count=len(lines.get(r.id, [])),
                component=r.id in components,
                review=r.review,
            )
            for r in recipes
        ],
        ingredients=[TopIngredient(id=i, name=n, recipes=c) for i, n, c in top],
        issues=[IssueSummary(id=i.id, label=i.label, published_on=i.published_on) for i in issues],
        episodes=[
            EpisodeSummary(
                id=e.id,
                name=episode_names[e.id],
                season=e.season,
                number=e.number,
                title=e.title,
                url=e.url,
                aired_on=e.aired_on,
            )
            for e in episodes
        ],
    )


@router.post(
    "",
    response_model=Added,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def add_by_isbn(
    body: AddByIsbn, admin: Contributing, session: Session, transport: Transport
) -> Added:
    """A book by its ISBN, from Open Library. A contributor's waits for
    review (migration 0041)."""
    try:
        isbn13 = isbn.normalise(body.isbn)
    except isbn.InvalidIsbn as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    # Checked before asking Open Library, so a book already here costs no request.
    existing = await session.scalar(select(Edition.source_id).where(Edition.isbn13 == isbn13))
    if existing is not None:
        raise await _already_here(session, admin, existing)
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
        raise await _already_here(session, admin, exc.source_id) from None
    await _mark_new(session, admin, source_id)
    await session.commit()
    log.info("%s added %s (%s)", admin.id, isbn13, found.title)
    return Added(id=source_id)


async def _already_here(session, user: User, source_id: uuid.UUID) -> HTTPException:
    """That book is here already: where, if the asker may see it. One
    someone else added that's waiting for review isn't pointed to."""
    source = await session.get_one(Source, source_id)
    if not await visibility.can_see(session, user, source):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "Someone has added that book already; it's waiting for review."},
        )
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {"message": "That edition is already in the catalog.", "source_id": str(source_id)},
    )


async def _mark_new(session, user: User, source_id: uuid.UUID) -> None:
    """Who added a new book; a contributor's waits for a moderator."""
    source = await session.get_one(Source, source_id)
    source.created_by = user.id
    if not user.publishes_directly:
        source.review = "pending"


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
async def add_without_isbn(
    body: WithoutIsbn, admin: Contributing, session: Session
) -> AddedManually:
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
    if existed:
        source = await session.get_one(Source, source_id)
        if not await visibility.can_see(session, admin, source):
            raise await _already_here(session, admin, source_id)
    else:
        await _mark_new(session, admin, source_id)
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
    if work.kind != "book":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a book links to Open Library.")
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
    source_id: uuid.UUID, body: LinkIn, admin: ModeratorUser, session: Session, transport: Transport
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
    source_id: uuid.UUID, body: LinkIn, admin: ModeratorUser, session: Session, transport: Transport
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
async def relink_references(
    source_id: uuid.UUID, admin: ModeratorUser, session: Session
) -> Relinked:
    """Link a book's page references again: for recipes stored before linking
    existed, which the Admin page runs over every book."""
    work = await session.get(Source, source_id)
    if work is None or not await visibility.can_see(session, admin, work):
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
    # A website's only; left as it is when not given.
    paywalled: bool | None = None


async def apply_book_edit(session, work: Source, body: BookIn) -> None:
    """Make the source say what the edit does (books.edit_book): the route's,
    and an applied proposal's (routers/proposals.py)."""
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
    if body.paywalled is not None:
        if work.kind != "website" and body.paywalled:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Only a website is behind a subscription."
            )
        work.paywalled = body.paywalled


def _may_change_book(user: User, work: Source) -> bool:
    if work.kind == "family":
        return False
    return user.may_edit or (
        user.may_claim and work.created_by == user.id and work.review != "published"
    )


@router.put("/{source_id}", response_model=Added, dependencies=[SameOrigin])
async def edit_book(source_id: uuid.UUID, body: BookIn, admin: Agreed, session: Session) -> Added:
    """Fix what a book says about itself (books.edit_book): a moderator, or
    the contributor who added it while it waits for review."""
    work = await session.get(Source, source_id)
    if work is None or not await visibility.can_see(session, admin, work):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    if not _may_change_book(admin, work):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a moderator can change that.")
    # Fixed after being sent back: waiting again.
    if work.review == "returned" and not admin.may_edit:
        work.review = "pending"
    await apply_book_edit(session, work, body)
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
    source_id: uuid.UUID, admin: ModeratorUser, session: Session, transport: Transport
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
    source_id: uuid.UUID, body: TakeIn, admin: ModeratorUser, session: Session, transport: Transport
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


class WebsiteIn(BaseModel):
    # Any address on the site, or just its host.
    address: str = Field(max_length=2000)
    # What the site calls itself ("Smitten Kitchen"); its host when not given.
    name: str | None = Field(default=None, max_length=300)
    paywalled: bool = False
    # Who writes it, in order, credited as authors.
    authors: list[str] = Field(default=[], max_length=30)


@router.post("/websites", response_model=AddedManually, dependencies=AGREED)
async def add_website(body: WebsiteIn, admin: ModeratorUser, session: Session) -> AddedManually:
    """A website as a source, one per site: the one already here for that
    host if there is one. Nothing is fetched from the site (web.py)."""
    try:
        host = web.site(body.address)
    except web.BadAddress as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    existing = await session.scalar(select(Source).where(Source.host == host))
    if existing is not None:
        return AddedManually(id=existing.id, existing=True)
    site = Source(
        kind="website",
        host=host,
        title=" ".join((body.name or "").split()) or host,
        paywalled=body.paywalled,
    )
    session.add(site)
    await session.flush()
    names = [n for n in (" ".join(a.split()) for a in body.authors) if n]
    for position, name in enumerate(dict.fromkeys(names), start=1):
        author = await books_module.author_named(session, name)
        session.add(
            SourceCredit(
                source_id=site.id, author_id=author.id, position=position, credited_as=name
            )
        )
    await session.commit()
    log.info("%s added the website %s", admin.id, host)
    return AddedManually(id=site.id, existing=False)


class PeriodicalIn(BaseModel):
    kind: Literal["magazine", "newspaper"]
    title: str = Field(max_length=300)
    # Its editors or regular writers, in order, credited as authors.
    authors: list[str] = Field(default=[], max_length=30)


class ShowIn(BaseModel):
    kind: Literal["tv_show", "podcast", "video_channel"]
    title: str = Field(max_length=300)
    # Its hosts, in order, credited as authors.
    authors: list[str] = Field(default=[], max_length=30)


@router.post("/periodicals", response_model=AddedManually, dependencies=AGREED)
async def add_periodical(
    body: PeriodicalIn, admin: ModeratorUser, session: Session
) -> AddedManually:
    """A magazine or newspaper as a source: the one already here of that
    kind and name, or a new one. Its issues are added as recipes name them."""
    return await _add_named(session, admin, body.kind, body.title, body.authors)


@router.post("/shows", response_model=AddedManually, dependencies=AGREED)
async def add_show(body: ShowIn, admin: ModeratorUser, session: Session) -> AddedManually:
    """A TV show, podcast or video channel as a source: the one already here
    of that kind and name, or a new one. Its episodes are added as recipes
    name them."""
    return await _add_named(session, admin, body.kind, body.title, body.authors)


class NamedIn(BaseModel):
    title: str = Field(max_length=300)
    # Who it is, or who makes it, in order, credited as authors.
    authors: list[str] = Field(default=[], max_length=30)


@router.post("/social", response_model=AddedManually, dependencies=AGREED)
async def add_social(body: NamedIn, admin: ModeratorUser, session: Session) -> AddedManually:
    """A social media account as a source, on any platform: the one already
    here by that name, or a new one. Its recipes are on its posts, by
    address."""
    return await _add_named(session, admin, "social", body.title, body.authors)


@router.post("/packaging", response_model=AddedManually, dependencies=AGREED)
async def add_packaging(body: NamedIn, admin: ModeratorUser, session: Session) -> AddedManually:
    """A product whose packaging prints recipes: the one already here by that
    name, or a new one."""
    return await _add_named(session, admin, "packaging", body.title, body.authors)


async def _add_named(
    session: Session, admin: ModeratorUser, kind: str, title: str, authors: list[str]
) -> AddedManually:
    """A source known only by its kind and name."""
    title = " ".join(title.split())
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give it its name.")
    existing = await session.scalar(
        select(Source).where(Source.kind == kind, func.lower(Source.title) == title.lower())
    )
    if existing is not None:
        return AddedManually(id=existing.id, existing=True)
    source = Source(kind=kind, title=title)
    session.add(source)
    await session.flush()
    names = [n for n in (" ".join(a.split()) for a in authors) if n]
    for position, name in enumerate(dict.fromkeys(names), start=1):
        author = await books_module.author_named(session, name)
        session.add(
            SourceCredit(
                source_id=source.id, author_id=author.id, position=position, credited_as=name
            )
        )
    await session.commit()
    log.info("%s added the %s %s", admin.id, kind, title)
    return AddedManually(id=source.id, existing=False)


class FamilyIn(BaseModel):
    title: str = Field(max_length=300)
    # Only its owner sees it. Until contributions are reviewed, only an
    # admin can add a public one.
    private: bool = True
    # The form's tick box: they understand what the site keeps, and who
    # sees it. Required; when it was ticked is kept.
    acknowledged: bool = False


class FamilyChange(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    private: bool | None = None


def _check_public(user: CurrentUser, private: bool) -> None:
    if not private and not user.may_edit:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "A family collection stays private until OpenLarder reviews what people add.",
        )


@router.post("/family", response_model=AddedManually, dependencies=[SameOrigin])
async def add_family(body: FamilyIn, user: CurrentUser, session: Session) -> AddedManually:
    """A family collection of the signed-in person's: one of theirs already
    of that name, or a new one. Anyone signed in can add one."""
    title = " ".join(body.title.split())
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give it its name.")
    if not body.acknowledged:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Tick that you understand what OpenLarder keeps and who sees it.",
        )
    _check_public(user, body.private)
    existing = await session.scalar(
        select(Source).where(
            Source.kind == "family",
            Source.owner_id == user.id,
            func.lower(Source.title) == title.lower(),
        )
    )
    if existing is not None:
        return AddedManually(id=existing.id, existing=True)
    collection = Source(
        kind="family",
        title=title,
        owner_id=user.id,
        private=body.private,
        acknowledged_at=func.now(),
    )
    session.add(collection)
    await session.commit()
    return AddedManually(id=collection.id, existing=False)


async def _family_or_404(session: Session, source_id: uuid.UUID, user: CurrentUser) -> Source:
    collection = await session.get(Source, source_id)
    if collection is None or not await visibility.can_see(session, user, collection):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such source.")
    if collection.kind != "family":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a family collection is changed here.")
    if not visibility.may_manage(user, collection):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only its owner can change it.")
    return collection


@router.patch("/{source_id}/family", response_model=Added, dependencies=[SameOrigin])
async def change_family(
    source_id: uuid.UUID, body: FamilyChange, user: CurrentUser, session: Session
) -> Added:
    """Rename a family collection, or make it private or public."""
    collection = await _family_or_404(session, source_id, user)
    if body.title is not None:
        title = " ".join(body.title.split())
        if not title:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give it its name.")
        collection.title = title
    if body.private is not None:
        _check_public(user, body.private)
        collection.private = body.private
    await session.commit()
    return Added(id=collection.id)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SameOrigin])
async def remove_family(source_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    """Delete a family collection and its recipes. Only a family collection
    can be deleted, by whoever may change it."""
    collection = await _family_or_404(session, source_id, user)
    await session.delete(collection)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _shared_with(session: Session, work: Source, viewer) -> list[GroupRef]:
    if work.kind != "family" or viewer is None:
        return []
    query = (
        select(Group.id, Group.name)
        .join(SourceGroup, SourceGroup.group_id == Group.id)
        .where(SourceGroup.source_id == work.id)
        .order_by(func.lower(Group.name), Group.id)
    )
    if not visibility.may_manage(viewer, work):
        query = query.join(
            GroupMember,
            (GroupMember.group_id == Group.id) & (GroupMember.user_id == viewer.id),
        )
    return [GroupRef(id=i, name=n) for i, n in await session.execute(query)]


class SharingIn(BaseModel):
    # Every group it's shared with; any left out stop seeing it.
    groups: list[uuid.UUID] = Field(max_length=50)


@router.put("/{source_id}/groups", response_model=list[GroupRef], dependencies=[SameOrigin])
async def share(
    source_id: uuid.UUID, body: SharingIn, user: CurrentUser, session: Session
) -> list[GroupRef]:
    """Choose which of your groups see a family collection of yours. Joining a
    group shares nothing by itself (Ray, 2026-11-08)."""
    collection = await _family_or_404(session, source_id, user)
    chosen = set(body.groups)
    mine = set(
        (
            await session.scalars(
                select(GroupMember.group_id).where(
                    GroupMember.user_id == user.id, GroupMember.group_id.in_(chosen)
                )
            )
        ).all()
    )
    if chosen - mine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You can only share with groups you're in.")
    await session.execute(
        delete(SourceGroup).where(
            SourceGroup.source_id == collection.id, SourceGroup.group_id.not_in(chosen)
        )
    )
    held = set(
        (
            await session.scalars(
                select(SourceGroup.group_id).where(SourceGroup.source_id == collection.id)
            )
        ).all()
    )
    for group_id in chosen - held:
        session.add(SourceGroup(source_id=collection.id, group_id=group_id))
    await session.commit()
    return await _shared_with(session, collection, user)


# Merging two records of one book (book_merge.py)


class MergeInto(BaseModel):
    into: uuid.UUID


class MergePlan(BaseModel):
    editions: int
    recipes: int
    credits: int
    same_titles: list[str]


async def _two_books(session, user: User, gone_id: uuid.UUID, kept_id: uuid.UUID):
    gone, kept = await session.get(Source, gone_id), await session.get(Source, kept_id)
    for source in (gone, kept):
        if source is None or not await visibility.can_see(session, user, source):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    return gone, kept


@router.get("/{source_id}/merge", response_model=MergePlan)
async def merge_plan(
    source_id: uuid.UUID, into: uuid.UUID, admin: ModeratorUser, session: Session
) -> MergePlan:
    """What merging this book into another would move."""
    gone, kept = await _two_books(session, admin, source_id, into)
    try:
        found = await book_merge.plan(session, gone, kept)
    except book_merge.CantMerge as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return MergePlan(**found.__dict__)


@router.post("/{source_id}/merge", response_model=Added, dependencies=AGREED)
async def merge_book(
    source_id: uuid.UUID, body: MergeInto, admin: ModeratorUser, session: Session
) -> Added:
    """Merge this book into another; answers with the one that's left."""
    gone, kept = await _two_books(session, admin, source_id, body.into)
    await history.via(session, f"merge:{gone.id}")
    try:
        await book_merge.merge(session, gone, kept, admin)
    except book_merge.CantMerge as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await session.commit()
    log.info("%s merged book %s into %s", admin.id, source_id, body.into)
    return Added(id=kept.id)
