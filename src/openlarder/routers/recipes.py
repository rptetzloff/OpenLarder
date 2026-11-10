"""Recipe entries: read one, and add, change or remove one (admins only).

An entry is where a recipe is and what goes in it, never how much or how;
see recipes.py.

Reading is public. Writing is for admins until review exists, like books.
"""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from openlarder import (
    archiving,
    buying,
    detector,
    ingredients,
    openlibrary,
    recipes,
    references,
    substitutions,
    visibility,
)
from openlarder import lines as line_reading
from openlarder.archiving import ArchiverDep
from openlarder.auth import CurrentUser, SameOrigin, Viewer
from openlarder.buying import BuyLink
from openlarder.db import Session
from openlarder.models import (
    Edition,
    Episode,
    Ingredient,
    IngredientOption,
    Issue,
    Recipe,
    RecipeIngredient,
    RecipeLocation,
    Source,
    SourceCredit,
    User,
    WebPage,
)
from openlarder.routers.substitutions import SwapOut, swap_out
from openlarder.tagging import RecipeTagOut, recipe_tags

router = APIRouter(tags=["recipes"])


class LinesIn(BaseModel):
    # Blank lines count here, though saving drops them.
    lines: list[str] = Field(max_length=2 * recipes.MAX_LINES)
    # The source the recipe is in, to say which of its recipes a page
    # reference means; and the recipe, when it's being changed, so it
    # doesn't cite itself.
    source_id: uuid.UUID | None = None
    recipe_id: uuid.UUID | None = None


class Named(BaseModel):
    id: uuid.UUID
    name: str


class OptionRead(BaseModel):
    name: str
    page: str | None
    # A page reference: the recipe in the source it means, and its pages.
    recipe: Named | None = None
    recipe_pages: list[str] = []
    # Unlinked, whether the page it cites holds other recipes: "isn't
    # linked" rather than "nothing there yet".
    page_used: bool = False
    # Otherwise the ingredient it will be matched to, if there is one, and
    # whether by another of its names.
    ingredient: Named | None = None
    alias: bool = False
    # When there isn't: ingredients named like it.
    similar: list[Named] = []


class LineReview(BaseModel):
    problems: list[str]
    suggestion: str | None
    remove: bool
    # Saving refuses the line as it is: it starts with an amount and a unit.
    refused: bool = False
    # How the line reads, once the rules have nothing to say about it.
    options: list[OptionRead] = []


class LinesReviewed(BaseModel):
    lines: list[LineReview]


# Looking for names like each unmatched option is a query apiece.
MAX_SIMILAR = 30


@router.post("/api/ingredient-lines/check", response_model=LinesReviewed, dependencies=[SameOrigin])
async def check_lines(body: LinesIn, session: Session, user: CurrentUser) -> LinesReviewed:
    """What the entry rules say about each line, and what each will be
    matched to, for the form to show as it's typed. Changes nothing; saving
    doesn't depend on it.

    An ingredient only a recipe the person can't see uses is left out, as
    everywhere: they're told the line is new."""
    entered = [line[: recipes.MAX_LINE] for line in body.lines]
    reviews = detector.review_all(entered)
    book: list[line_reading.BookRecipe] = []
    by_title: dict = {}
    if body.source_id:
        await _editable_source(session, body.source_id, user)
        book, by_title = await references.book_recipes(session, body.source_id)
    titles = {r.id: r.title for r in book}
    citing = body.recipe_id or uuid.uuid4()

    read: list[list[OptionRead]] = []
    for line, review in zip(entered, reviews, strict=True):
        options = []
        if line.strip() and not review.problems:
            for option in line_reading.options(" ".join(line.split())):
                found = OptionRead(name=option.name, page=option.page)
                if option.page is not None and book:
                    resolved = line_reading.resolve(citing, option, book, by_title)
                    if resolved.recipe_id:
                        found.recipe = Named(id=resolved.recipe_id, name=titles[resolved.recipe_id])
                        found.recipe_pages = sorted(
                            next(r.pages for r in book if r.id == resolved.recipe_id)
                        )
                    else:
                        found.page_used = any(
                            option.page in r.pages for r in book if r.id != body.recipe_id
                        )
                options.append(found)
        read.append(options)

    seen = visibility.ingredients_seen_by(user)
    named = [o for options in read for o in options if o.page is None]
    matched = await ingredients.known(session, {ingredients.match_key(o.name) for o in named}, seen)
    looked = 0
    for option in named:
        if hit := matched.get(ingredients.match_key(option.name)):
            option.ingredient = Named(id=hit[0], name=hit[1])
            option.alias = hit[2]
        elif looked < MAX_SIMILAR:
            looked += 1
            option.similar = [
                Named(id=i, name=n) for i, n in await ingredients.like(session, option.name, seen)
            ]
    return LinesReviewed(
        lines=[
            LineReview(
                problems=r.problems,
                suggestion=r.suggestion,
                remove=r.remove,
                refused=bool(recipes.AMOUNT.match(" ".join(line.split()))),
                options=o,
            )
            for line, r, o in zip(entered, reviews, read, strict=True)
        ]
    )


class PageIn(BaseModel):
    edition_id: uuid.UUID
    page: str | None = None


class EpisodeIn(BaseModel):
    # Any of these says which episode: its number (in its season), its
    # title, or a video's or podcast episode's address.
    season: int | None = None
    number: int | None = None
    title: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=2000)
    aired_on: date | None = None
    # Where in it the recipe starts: 12:34, or 1:02:03.
    at: str | None = Field(default=None, max_length=20)


class RecipeIn(BaseModel):
    title: str
    # A book's recipe: the editions it's in, each with its page.
    editions: list[PageIn] = []
    # A website's recipe instead: the page's address.
    web_address: str | None = Field(default=None, max_length=2000)
    # A magazine's or newspaper's: the issue (its name, or its date), and the
    # page in it.
    issue: str | None = Field(default=None, max_length=200)
    issue_date: date | None = None
    issue_page: str | None = Field(default=None, max_length=40)
    # A TV show's, podcast's or video channel's: the episode.
    episode: EpisodeIn | None = None
    # The chapter or section it's in, as the book names it.
    chapter: str | None = Field(default=None, max_length=200)
    ingredients: list[str] = []


class PageOut(BaseModel):
    edition_id: uuid.UUID
    edition_title: str | None
    isbn13: str | None
    published_year: int | None
    page: str | None
    cover_url: str | None = None
    # Where to buy this edition, through /go/; none until an affiliate ID.
    buy: list[BuyLink] = []


class WebPageOut(BaseModel):
    id: uuid.UUID
    url: str
    # The Internet Archive's copy, when there is one.
    archive_url: str | None
    archived_at: datetime | None
    # Marked when the page no longer has the recipe.
    gone: bool


class IssueOut(BaseModel):
    id: uuid.UUID
    label: str
    published_on: date | None
    # The recipe's page in it.
    page: str | None


class EpisodeOut(BaseModel):
    id: uuid.UUID
    # How it reads: Season 2, episode 5, “Fat”.
    name: str
    season: int | None
    number: int | None
    title: str | None
    url: str | None
    aired_on: date | None
    # Where in it the recipe starts, as 12:34.
    at: str | None


class CreditRef(BaseModel):
    author_id: uuid.UUID
    credited_as: str


class SourceRef(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    # Who it credits, in order, as it prints them.
    credits: list[CreditRef] = []


class RecipeLink(BaseModel):
    id: uuid.UUID
    title: str


class UsedIn(RecipeLink):
    # Its page, where it has one: the newest edition's it's in.
    page: str | None = None


class IngredientLink(BaseModel):
    id: uuid.UUID
    name: str


class OptionOut(BaseModel):
    name: str
    # The page the line cites, as written; the linked recipe's own page can
    # differ, when the line has it wrong.
    page: str | None
    recipe: RecipeLink | None
    ingredient: IngredientLink | None


class LineOut(BaseModel):
    text: str
    options: list[OptionOut]


class RecipeOut(BaseModel):
    id: uuid.UUID
    title: str
    # The chapter or section of its book, as the book names it.
    chapter: str | None
    # Its tags, and its source's (from_source).
    tags: list[RecipeTagOut] = []
    source: SourceRef
    # A book's recipe: where it is in each edition.
    pages: list[PageOut]
    # A website's recipe: the page it's on, and that page's archived copy.
    web_address: str | None
    web_page: WebPageOut | None
    # A magazine's or newspaper's recipe: the issue it's in, at its page.
    issue: IssueOut | None
    # A TV show's, podcast's or video channel's: the episode, at its time.
    episode: EpisodeOut | None
    # The lines as typed, which is what the edit form edits.
    ingredients: list[str]
    # The same lines read into their options, with page references linked.
    lines: list[LineOut]
    # Recipes in the book that use this one as a component.
    used_in: list[UsedIn]
    # What can stand in for its ingredients, the recipes it cites, or itself.
    swaps: list[SwapOut]
    # Whether the viewer may change or remove it.
    editable: bool
    # Who added it (their display name, public as on everything they add),
    # and when.
    added_by: str | None = None
    added_on: date | None = None


class Created(BaseModel):
    id: uuid.UUID


def _clean(body: RecipeIn) -> recipes.RecipeEntry:
    given = body.episode
    try:
        episode = (
            recipes.EpisodeEntry(
                season=given.season,
                number=given.number,
                title=given.title,
                url=given.address,
                aired_on=given.aired_on,
                at_seconds=recipes.seconds(given.at),
            )
            if given
            else None
        )
        return recipes.clean(
            body.title,
            [(p.edition_id, p.page) for p in body.editions],
            body.ingredients,
            web_address=body.web_address,
            issue=body.issue,
            issue_date=body.issue_date,
            issue_page=body.issue_page,
            episode=episode,
            chapter=body.chapter,
        )
    except recipes.InvalidRecipe as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


def _episode_out(episode: Episode, at: int | None) -> EpisodeOut:
    return EpisodeOut(
        id=episode.id,
        name=recipes.episode_name(episode.season, episode.number, episode.title),
        season=episode.season,
        number=episode.number,
        title=episode.title,
        url=episode.url,
        aired_on=episode.aired_on,
        at=recipes.clock(at) if at is not None else None,
    )


async def _recipe_or_404(session, recipe_id: uuid.UUID, viewer) -> Recipe:
    recipe = await session.get(Recipe, recipe_id)
    if recipe is None or not await visibility.can_see(
        session, viewer, await session.get_one(Source, recipe.source_id)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe.")
    return recipe


async def _editable_source(session, source_id: uuid.UUID, user) -> Source:
    """The source, when the user may add to and change it: 404 when they
    can't see it, 403 when they can but it isn't theirs to change."""
    source = await session.get(Source, source_id)
    if source is None or not await visibility.can_see(session, user, source):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such source.")
    if not await visibility.may_edit(session, user, source):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can change that.")
    return source


async def _out(session, recipe: Recipe, viewer) -> RecipeOut:
    work = await session.get_one(Source, recipe.source_id)
    pages = (
        await session.execute(
            select(RecipeLocation.page, Edition)
            .join(Edition, Edition.id == RecipeLocation.edition_id)
            .where(RecipeLocation.recipe_id == recipe.id)
            .order_by(Edition.published_year.desc().nulls_last(), Edition.isbn13)
        )
    ).all()
    in_issue = (
        await session.execute(
            select(Issue, RecipeLocation.page)
            .join(RecipeLocation, RecipeLocation.issue_id == Issue.id)
            .where(RecipeLocation.recipe_id == recipe.id)
        )
    ).first()
    in_episode = (
        await session.execute(
            select(Episode, RecipeLocation.at_seconds)
            .join(RecipeLocation, RecipeLocation.episode_id == Episode.id)
            .where(RecipeLocation.recipe_id == recipe.id)
        )
    ).first()
    page = await session.scalar(
        select(WebPage)
        .join(RecipeLocation, RecipeLocation.web_page_id == WebPage.id)
        .where(RecipeLocation.recipe_id == recipe.id)
    )
    lines = (
        await session.execute(
            select(RecipeIngredient.id, RecipeIngredient.original_text)
            .where(RecipeIngredient.recipe_id == recipe.id)
            .order_by(RecipeIngredient.position)
        )
    ).all()
    linked: dict[uuid.UUID, dict[int, RecipeLink]] = {}
    matched: dict[uuid.UUID, dict[int, IngredientLink]] = {}
    for line_id, rank, ingredient_id, name in await session.execute(
        select(
            IngredientOption.recipe_ingredient_id,
            IngredientOption.rank,
            Ingredient.id,
            Ingredient.name,
        )
        .join(Ingredient, Ingredient.id == IngredientOption.ingredient_id)
        .where(IngredientOption.recipe_id == recipe.id)
    ):
        matched.setdefault(line_id, {})[rank] = IngredientLink(id=ingredient_id, name=name)
    for line_id, rank, sub_id, sub_title in await session.execute(
        select(
            IngredientOption.recipe_ingredient_id,
            IngredientOption.rank,
            Recipe.id,
            Recipe.title,
        )
        .join(Recipe, Recipe.id == IngredientOption.sub_recipe_id)
        .where(IngredientOption.recipe_id == recipe.id)
    ):
        linked.setdefault(line_id, {})[rank] = RecipeLink(id=sub_id, title=sub_title)
    used_in = (
        await session.execute(
            select(Recipe.id, Recipe.title)
            .join(IngredientOption, IngredientOption.recipe_id == Recipe.id)
            .where(IngredientOption.sub_recipe_id == recipe.id)
            .distinct()
            .order_by(Recipe.title)
        )
    ).all()
    used_pages: dict[uuid.UUID, str] = {}
    for user_id, its_page in await session.execute(
        select(RecipeLocation.recipe_id, RecipeLocation.page)
        .join(Edition, Edition.id == RecipeLocation.edition_id)
        .where(
            RecipeLocation.recipe_id.in_([u for u, _ in used_in]),
            RecipeLocation.page.is_not(None),
        )
        .order_by(Edition.published_year.desc().nulls_last())
    ):
        used_pages.setdefault(user_id, its_page)
    credits = (
        await session.execute(
            select(SourceCredit.author_id, SourceCredit.credited_as)
            .where(SourceCredit.source_id == work.id)
            .order_by(SourceCredit.position)
        )
    ).all()
    adder = await session.get(User, recipe.created_by) if recipe.created_by else None
    return RecipeOut(
        id=recipe.id,
        title=recipe.title,
        chapter=recipe.chapter,
        tags=await recipe_tags(session, recipe),
        source=SourceRef(
            id=work.id,
            title=work.title,
            kind=work.kind,
            credits=[CreditRef(author_id=a, credited_as=n) for a, n in credits],
        ),
        web_address=page.url if page else None,
        issue=IssueOut(
            id=in_issue[0].id,
            label=in_issue[0].label,
            published_on=in_issue[0].published_on,
            page=in_issue[1],
        )
        if in_issue
        else None,
        episode=_episode_out(*in_episode) if in_episode else None,
        web_page=WebPageOut(
            id=page.id,
            url=page.url,
            archive_url=page.archive_url,
            archived_at=page.archived_at,
            gone=page.gone,
        )
        if page
        else None,
        pages=[
            PageOut(
                edition_id=e.id,
                edition_title=e.title,
                isbn13=e.isbn13,
                published_year=e.published_year,
                page=page,
                cover_url=(
                    openlibrary.cover_url(e.open_library_cover_id)
                    if e.open_library_cover_id
                    else None
                ),
                buy=buying.links(e.id, e.isbn13, work.kind),
            )
            for page, e in pages
        ],
        ingredients=[text for _, text in lines],
        lines=[
            LineOut(
                text=text,
                options=[
                    OptionOut(
                        name=option.name,
                        page=option.page,
                        recipe=linked.get(line_id, {}).get(rank),
                        ingredient=matched.get(line_id, {}).get(rank),
                    )
                    for rank, option in enumerate(line_reading.options(text), start=1)
                ],
            )
            for line_id, text in lines
        ],
        used_in=[UsedIn(id=i, title=t, page=used_pages.get(i)) for i, t in used_in],
        added_by=adder.display_name if adder else None,
        added_on=recipe.created_at.date() if recipe.created_at else None,
        swaps=[
            swap_out(x)
            for x in await substitutions.listed(session, substitutions.for_recipe(recipe.id))
        ],
        editable=viewer is not None and await visibility.may_edit(session, viewer, work),
    )


@router.get("/api/recipes/{recipe_id}", response_model=RecipeOut)
async def get_recipe(recipe_id: uuid.UUID, session: Session, viewer: Viewer) -> RecipeOut:
    return await _out(session, await _recipe_or_404(session, recipe_id, viewer), viewer)


class RecipeLines(BaseModel):
    id: uuid.UUID
    lines: list[str]


@router.get("/api/sources/{source_id}/recipe-lines", response_model=list[RecipeLines])
async def source_recipe_lines(
    source_id: uuid.UUID, session: Session, viewer: Viewer
) -> list[RecipeLines]:
    """Every recipe's ingredient lines as typed, for entering a whole book:
    the source's page gives only the first few of each."""
    source = await session.get(Source, source_id)
    if source is None or not await visibility.can_see(session, viewer, source):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such source.")
    found: dict[uuid.UUID, list[str]] = {
        r: [] for r in await session.scalars(select(Recipe.id).where(Recipe.source_id == source_id))
    }
    for recipe_id, text in await session.execute(
        select(RecipeIngredient.recipe_id, RecipeIngredient.original_text)
        .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
        .where(Recipe.source_id == source_id)
        .order_by(RecipeIngredient.recipe_id, RecipeIngredient.position)
    ):
        found[recipe_id].append(text)
    return [RecipeLines(id=r, lines=lines) for r, lines in found.items()]


@router.post(
    "/api/sources/{source_id}/recipes",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def add_recipe(
    source_id: uuid.UUID,
    body: RecipeIn,
    user: CurrentUser,
    session: Session,
    background: BackgroundTasks,
    archiver: ArchiverDep,
) -> Created:
    await _editable_source(session, source_id, user)
    entry = _clean(body)
    try:
        recipe = await recipes.create(session, source_id, entry)
    except recipes.InvalidRecipe as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    # Whoever added it deals with its flags (routers/flags.py).
    recipe.created_by = user.id
    await references.relink(session, source_id)
    await session.commit()
    if pages := await archiving.uncopied(session, recipe.id):
        background.add_task(archiver.run, pages)
    return Created(id=recipe.id)


@router.put("/api/recipes/{recipe_id}", response_model=RecipeOut, dependencies=[SameOrigin])
async def change_recipe(
    recipe_id: uuid.UUID,
    body: RecipeIn,
    user: CurrentUser,
    session: Session,
    background: BackgroundTasks,
    archiver: ArchiverDep,
) -> RecipeOut:
    recipe = await _recipe_or_404(session, recipe_id, user)
    await _editable_source(session, recipe.source_id, user)
    entry = _clean(body)
    try:
        await recipes.replace(session, recipe, entry)
    except recipes.InvalidRecipe as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await references.relink(session, recipe.source_id)
    await session.commit()
    if pages := await archiving.uncopied(session, recipe.id):
        background.add_task(archiver.run, pages)
    return await _out(session, recipe, user)


@router.delete(
    "/api/recipes/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SameOrigin],
)
async def remove_recipe(recipe_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    recipe = await _recipe_or_404(session, recipe_id, user)
    await _editable_source(session, recipe.source_id, user)
    source_id = recipe.source_id
    await references.release(session, recipe.id)
    await session.delete(recipe)
    await session.flush()
    await references.relink(session, source_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
