"""Search: what can I make from these books with what I have?

Public, like the rest of the catalog. Three things narrow it, alone or
together: ingredients you have, words of a title, and books.

**Ingredients you have** rank recipes rather than filter them strictly. A
recipe is found if any of its lines is covered. Recipes needing nothing
else come first, then the more of the recipe you have ("you have 5 of its
7" before "1 of 2"), then the fewer lines still needed; each lists what
it's missing. *Ray, 2026-11-08: "I have three
cookbooks pulled out... I have these ingredients".* A line is covered when
any of its options is one of your ingredients or one under it in the
hierarchy, so cheese covers "Aged Cheddar", and "Butter or Margarine" is
covered by either. Salt, pepper, sugar and water are left out of lines by
the entry rules, so they never count as missing. A line citing another
recipe is a component to make, not something you have, and counts as
missing.

**Only what you can make** (`missing_max`; *Ray, 2026-11-14*): with
ingredients or a larder, keeps the recipes missing at most that many lines:
0 for those you have everything for, or 1 or 2. What counts as missing is
as above, and doesn't change. Without ingredients it has nothing to count,
and does nothing.

**Title words** must all appear in the title, ignoring case; accents count,
as they do for ingredients. The trigram index on recipe titles serves them.
The closest titles come first (title_rank.py): the words as whole words,
then beginning a word, then inside one. With ingredients too, that only
orders recipes level on what you have.

**Your shelf** (routers/shelf.py): only the books you own, with any
sources chosen too.

**Saved** (routers/saved.py): only the recipes you've saved, or that are
on a list shared with you.

**Sources**: a recipe in any of them. IDs that name no ingredient or source now,
as after a merge, are left out of the search and reported, so an old link
still finds what it can. An ingredient's own page lists exactly the recipes
matched to it; this is the broader search.

**Equipment** (*Ray's equipment spec, 2026-11-15*) filters, where
ingredients rank. `needs`: only recipes needing each thing named, or
something that counts as it, so a mixer finds the recipes needing a stand
mixer; "Stand mixer or Hand mixer" needs either. Enough to search by, by
itself: "what can I make with my ice cream maker?". `no_equipment`: recipes
needing one are left out, as `without` leaves out an ingredient: a need
offering something else stays. A recipe whose equipment isn't recorded
needs nothing anyone knows of: `needs` never finds it and `no_equipment`
never hides it. Each hit says what it needs.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, exists, func, or_, select, union
from sqlalchemy.orm import aliased

from openlarder import equipment as kit
from openlarder import needs as recipe_needs
from openlarder import title_rank, visibility
from openlarder.auth import Viewer
from openlarder.db import Session
from openlarder.ingredients import family, rooted_ancestry, rooted_family
from openlarder.models import (
    Equipment,
    EquipmentOption,
    Ingredient,
    IngredientOption,
    LarderItem,
    LarderList,
    Recipe,
    RecipeEquipment,
    RecipeIngredient,
    RecipeTag,
    Source,
    SourceTag,
    Tag,
)
from openlarder.routers.ingredients import (
    UsedBy,
    contains_pattern,
    recipes_where,
    with_pages,
)
from openlarder.routers.larder import seen_list_ids
from openlarder.routers.ratings import best_first, rated
from openlarder.routers.saved import saved_recipe_ids
from openlarder.routers.shelf import shelf_source_ids
from openlarder.tagging import MAX_TAGS

router = APIRouter(prefix="/api/search", tags=["search"])

MAX_INGREDIENTS = 30
# Pieces of equipment to need, or to leave out, in one search.
MAX_EQUIPMENT = 30
# Larder lists or things named in one search.
MAX_LARDER_PICKS = 200
MAX_WORDS = 10
MAX_SOURCES = 10
# Results a page holds: the wireframe's short page, numbered (Ray,
# 2026-11-08).
PAGE = 20


class Named(BaseModel):
    id: uuid.UUID
    name: str


class Hit(UsedBy):
    # With ingredients: how many of the recipe's lines you have, of how
    # many, and the lines you don't, as the book names them.
    have: int | None = None
    lines: int | None = None
    needs: list[str] = []
    # Which of the ingredients you have it uses, in the order you gave them.
    uses: list[str] = []
    # What it can't be made without, each need as its recipe's page words
    # it ("Stand mixer or Hand mixer"). `needs` above was taken, by lines.
    equipment: list[str] = []


Kind = Literal[
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


class Found(BaseModel):
    # The sources searched within, if any were, in the order asked.
    sources: list[Named]
    # The ingredients searched for, in the order asked.
    ingredients: list[Named]
    # Those you don't have or want: recipes needing one are left out.
    without: list[Named] = []
    # Ingredient and source IDs asked for that name nothing now.
    missing: list[uuid.UUID]
    missing_sources: list[uuid.UUID]
    # Equipment every recipe found needs, and equipment none of them does,
    # in the order asked; and the IDs asked for that name nothing now.
    needing: list[Named] = []
    no_equipment: list[Named] = []
    missing_equipment: list[uuid.UUID] = []
    # The tags searched for, in the order asked, and those that are gone.
    tags: list[Named] = []
    missing_tags: list[uuid.UUID] = []
    # The title words searched for, tidied.
    q: str
    recipes: list[Hit]
    total: int
    # Recipes a page holds, so a listing can number its pages.
    per_page: int = 0
    # Searched with the viewer's larder: how many of its items counted
    # (have or running low, matched to an ingredient).
    larder_items: int | None = None
    # Kept to the viewer's shelf: how many books are on it.
    shelf_books: int | None = None


def _too_many(n: int, limit: int, what: str) -> None:
    if n > limit:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Search with at most {limit} {what}."
        )


@router.get("", response_model=Found)
async def search(
    session: Session,
    viewer: Viewer,
    ingredient: Annotated[list[uuid.UUID] | None, Query()] = None,
    q: str = Query("", max_length=200),
    source: Annotated[list[uuid.UUID] | None, Query()] = None,
    # Only these kinds of source: books, websites and so on.
    kind: Annotated[list[Kind] | None, Query()] = None,
    # Ingredients you don't have or want (Ray, 2026-11-08).
    without: Annotated[list[uuid.UUID] | None, Query()] = None,
    # Recipes with all of these tags, their own or their source's.
    tag: Annotated[list[uuid.UUID] | None, Query()] = None,
    # Only recipes needing all of this equipment (or what counts as it), and
    # none needing any of that.
    needing: Annotated[list[uuid.UUID] | None, Query(alias="needs")] = None,
    no_equipment: Annotated[list[uuid.UUID] | None, Query()] = None,
    # With what's in your larder, as well as any ingredients chosen: each
    # thing counts as itself and everything above it (Chipotle Hot Sauce is
    # hot sauce too). Ray, 2026-11-10. Narrowed to some lists (larder_list),
    # to some things (larder_item: only these), or less some (larder_without),
    # for a pantry the size of a restaurant's.
    larder: bool = False,
    larder_list: Annotated[list[uuid.UUID] | None, Query()] = None,
    larder_item: Annotated[list[uuid.UUID] | None, Query()] = None,
    larder_without: Annotated[list[uuid.UUID] | None, Query()] = None,
    # Only the books on your shelf (routers/shelf.py).
    shelf: bool = False,
    # Only the recipes you've saved (routers/saved.py).
    saved: bool = False,
    # "rating": the rated recipes first, best first, then the rest as they'd
    # come anyway (routers/ratings.py). Ray, 2026-11-12.
    sort: Literal["match", "rating"] = "match",
    missing_max: int | None = Query(
        None,
        ge=0,
        le=2,
        description=(
            "With ingredients or a larder: only recipes missing at most this many lines."
            " 0 keeps those you have everything for. Left out, ingredients rank recipes"
            " and don't filter them."
        ),
    ),
    offset: int = Query(0, ge=0),
) -> Found:
    stocked: list[uuid.UUID] = []
    if shelf and viewer is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to search your shelf.")
    if saved and viewer is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to search your saved recipes.")
    if larder:
        if viewer is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to search with your larder.")
        for given, what in (
            (larder_list, "lists"),
            (larder_item, "things"),
            (larder_without, "things to leave out"),
        ):
            _too_many(len(given or []), MAX_LARDER_PICKS, f"larder {what}")
        stocked = await larder_ingredients(
            session, viewer, larder_list or [], larder_item or [], larder_without or []
        )
    asked = list(dict.fromkeys(ingredient or []))
    unwanted = list(dict.fromkeys(without or []))
    words = list(dict.fromkeys(q.casefold().split()))
    picked = list(dict.fromkeys(source or []))
    tagged = list(dict.fromkeys(tag or []))
    wanted_kit = list(dict.fromkeys(needing or []))
    unwanted_kit = list(dict.fromkeys(no_equipment or []))
    if not asked and not words and not tagged and not larder and not saved and not wanted_kit:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Choose an ingredient, a tag or equipment, or type part of a title.",
        )
    _too_many(len(asked), MAX_INGREDIENTS, "ingredients")
    _too_many(len(words), MAX_WORDS, "words of a title")
    _too_many(len(picked), MAX_SOURCES, "sources")
    _too_many(len(unwanted), MAX_INGREDIENTS, "ingredients to leave out")
    _too_many(len(tagged), MAX_TAGS, "tags")
    _too_many(len(wanted_kit), MAX_EQUIPMENT, "pieces of equipment")
    _too_many(len(unwanted_kit), MAX_EQUIPMENT, "pieces of equipment to leave out")

    found_names = await session.execute(
        select(Ingredient.id, Ingredient.name).where(
            Ingredient.id.in_(asked + unwanted), visibility.ingredients_seen_by(viewer)
        )
    )
    names = {i: n for i, n in found_names}
    found_titles = await session.execute(
        select(Source.id, Source.title).where(
            Source.id.in_(picked), visibility.sources_seen_by(viewer)
        )
    )
    titles = {i: t for i, t in found_titles}
    tag_names = dict(
        (await session.execute(select(Tag.id, Tag.name).where(Tag.id.in_(tagged)))).all()
    )
    tags_known = [i for i in tagged if i in tag_names]
    # A thing that isn't in the list is named only to someone who sees a
    # recipe needing it; to anyone else it's one that's gone.
    kit_names = dict(
        (
            await session.execute(
                select(Equipment.id, Equipment.name).where(
                    Equipment.id.in_(wanted_kit + unwanted_kit),
                    visibility.equipment_seen_by(viewer),
                )
            )
        ).all()
    )
    kit_needed = [i for i in wanted_kit if i in kit_names]
    kit_left_out = [i for i in unwanted_kit if i in kit_names]
    known = [i for i in asked if i in names]
    books = [i for i in picked if i in titles]
    found = Found(
        sources=[Named(id=i, name=titles[i]) for i in books],
        ingredients=[Named(id=i, name=names[i]) for i in known],
        without=[Named(id=i, name=names[i]) for i in unwanted if i in names],
        missing=[i for i in asked + unwanted if i not in names],
        missing_sources=[i for i in picked if i not in titles],
        needing=[Named(id=i, name=kit_names[i]) for i in kit_needed],
        no_equipment=[Named(id=i, name=kit_names[i]) for i in kit_left_out],
        missing_equipment=[
            i for i in dict.fromkeys(wanted_kit + unwanted_kit) if i not in kit_names
        ],
        tags=[Named(id=i, name=tag_names[i]) for i in tags_known],
        missing_tags=[i for i in tagged if i not in tag_names],
        q=" ".join(q.split()),
        recipes=[],
        total=0,
        # Read at call time, so a test can shrink it.
        per_page=PAGE,
    )
    if shelf:
        found.shelf_books = await session.scalar(
            select(func.count()).select_from(shelf_source_ids(viewer).subquery())
        )
        if not found.shelf_books:
            return found
    if larder:
        found.larder_items = len(stocked)
        if not stocked and not known:
            return found
    # Everything asked for is gone: nothing left to search by.
    if not known and not words and not tags_known and not stocked and not saved and not kit_needed:
        return found
    conditions = [Recipe.title.ilike(contains_pattern(w), escape="\\") for w in words]
    conditions.append(visibility.recipes_seen_by(viewer))
    if kind:
        conditions.append(Recipe.source_id.in_(select(Source.id).where(Source.kind.in_(kind))))
    if books:
        conditions.append(Recipe.source_id.in_(books))
    if shelf:
        conditions.append(Recipe.source_id.in_(shelf_source_ids(viewer)))
    if saved:
        conditions.append(Recipe.id.in_(saved_recipe_ids(viewer)))
    for t in tags_known:
        conditions.append(
            exists().where(RecipeTag.recipe_id == Recipe.id, RecipeTag.tag_id == t)
            | Recipe.source_id.in_(select(SourceTag.source_id).where(SourceTag.tag_id == t))
        )
    left_out = [i for i in unwanted if i in names]
    if left_out:
        conditions.append(~_needs_any(left_out))
    for n, thing in enumerate(kit_needed):
        conditions.append(_can_use(thing, n))
    if kit_left_out:
        conditions.append(~_cant_do_without(kit_left_out))
    by_rating = sort == "rating"
    title = (words, found.q) if words else None
    if stocked:
        found.recipes, found.total = await _best_match(
            session,
            known,
            conditions,
            offset,
            upward=stocked,
            by_rating=by_rating,
            title=title,
            missing_max=missing_max,
        )
    elif not known:
        page, found.total = await recipes_where(
            session, *conditions, offset=offset, limit=PAGE, by_rating=by_rating, title=title
        )
        found.recipes = [Hit(**r.model_dump()) for r in page]
    else:
        found.recipes, found.total = await _best_match(
            session,
            known,
            conditions,
            offset,
            by_rating=by_rating,
            title=title,
            missing_max=missing_max,
        )
    listed = await recipe_needs.of_recipes(session, [r.id for r in found.recipes])
    for hit in found.recipes:
        hit.equipment = [
            recipe_needs.as_typed(detail, things) for _, detail, things in listed.get(hit.id, [])
        ]
    return found


async def larder_ingredients(
    session: Session,
    viewer,
    lists: list[uuid.UUID] = (),
    items: list[uuid.UUID] = (),
    without: list[uuid.UUID] = (),
) -> list[uuid.UUID]:
    """The ingredients the viewer's larder has (have or running low): their
    lists and those shared with them, of the ingredients they may see; only
    the things named, if some are, or else only the lists named, if some
    are; less the things left out."""
    query = (
        select(func.distinct(LarderItem.ingredient_id))
        .join(LarderList, LarderList.id == LarderItem.list_id)
        .join(Ingredient, Ingredient.id == LarderItem.ingredient_id)
        .where(
            LarderList.id.in_(seen_list_ids(viewer)),
            LarderItem.state.in_(("have", "low")),
            visibility.ingredients_seen_by(viewer),
        )
    )
    if items:
        query = query.where(LarderItem.id.in_(items))
    elif lists:
        query = query.where(LarderList.id.in_(lists))
    if without:
        query = query.where(LarderItem.id.not_in(without))
    return list(await session.scalars(query))


def _needs_any(unwanted: list[uuid.UUID]):
    """A recipe needs one of these when a line of it names one (or one under
    it) and offers nothing else: "Butter or Coconut Oil" doesn't need butter.
    A sub-recipe as a choice is something else."""
    banned = family(*unwanted, name="unwanted")
    line = aliased(RecipeIngredient)
    banned_choice = aliased(IngredientOption)
    other_choice = aliased(IngredientOption)
    return exists().where(
        line.recipe_id == Recipe.id,
        exists().where(
            banned_choice.recipe_ingredient_id == line.id,
            banned_choice.ingredient_id.in_(banned),
        ),
        ~exists().where(
            other_choice.recipe_ingredient_id == line.id,
            or_(other_choice.ingredient_id.is_(None), other_choice.ingredient_id.not_in(banned)),
        ),
    )


def _can_use(wanted: uuid.UUID, n: int):
    """A recipe can use a thing when one of its needs is met by it, or by
    something that counts as it: asked for a mixer, a recipe needing "Stand
    mixer or Hand mixer" is one, and so is it asked for a stand mixer. n
    keeps the names apart when several things are asked for."""
    met = aliased(EquipmentOption)
    return exists().where(
        met.recipe_id == Recipe.id,
        met.equipment_id.in_(kit.family(wanted, name=f"needed_equipment_{n}")),
    )


def _cant_do_without(unwanted: list[uuid.UUID]):
    """A recipe can't do without one of these when a need of it names one
    (or something that counts as one) and offers nothing else: "Stand mixer
    or Whisk" can do without a stand mixer. As _needs_any is for
    ingredients."""
    banned = kit.family(*unwanted, name="unwanted_equipment")
    need = aliased(RecipeEquipment)
    banned_choice = aliased(EquipmentOption)
    other_choice = aliased(EquipmentOption)
    return exists().where(
        need.recipe_id == Recipe.id,
        exists().where(
            banned_choice.recipe_equipment_id == need.id,
            banned_choice.equipment_id.in_(banned),
        ),
        ~exists().where(
            other_choice.recipe_equipment_id == need.id,
            other_choice.equipment_id.not_in(banned),
        ),
    )


def _yours(down: list[uuid.UUID], up: list[uuid.UUID], name: str):
    """(root, id) for what you have: an ingredient chosen and everything
    under it (cheese finds cheddar), and a larder's thing and everything
    above it (chipotle hot sauce is hot sauce)."""
    parts = []
    if down:
        tree = rooted_family(*down, name=f"{name}_down")
        parts.append(select(tree.c.root, tree.c.id))
    if up:
        tree = rooted_ancestry(*up, name=f"{name}_up")
        parts.append(select(tree.c.root, tree.c.id))
    return (union(*parts) if len(parts) > 1 else parts[0]).subquery(name)


async def _best_match(
    session: Session,
    chosen: list[uuid.UUID],
    conditions,
    offset: int,
    upward: list[uuid.UUID] = (),
    by_rating: bool = False,
    title: tuple[list[str], str] | None = None,
    missing_max: int | None = None,
):
    """Recipes covering any line with what you have: those using the most of
    your ingredients first, then by the share of their lines you have (so
    complete ones come first), fewest still needed, then book and title.
    *Ray, 2026-11-08:* frog's legs and garlic should put the recipes using
    both first; ranking by share alone put one-line garlic pastes there.
    by_rating: the rated ones first, best first, then the rest that way.
    title: a title search's words and the search as typed; recipes level
    on what you have come closest title first (title_rank.py).
    missing_max: only those with at most this many lines not covered."""
    # Which of yours each match is under (or, from a larder, above): to count
    # how many of yours a recipe uses, and to say which.
    have = list(dict.fromkeys([*chosen, *upward]))
    roots = _yours(list(chosen), list(upward), "yours_by_root")
    yours = select(_yours(list(chosen), list(upward), "yours").c.id)
    used = (
        select(
            IngredientOption.recipe_id.label("recipe_id"),
            func.count(func.distinct(roots.c.root)).label("used"),
        )
        .join(roots, roots.c.id == IngredientOption.ingredient_id)
        .group_by(IngredientOption.recipe_id)
        .subquery()
    )
    covered = exists().where(
        IngredientOption.recipe_ingredient_id == RecipeIngredient.id,
        IngredientOption.ingredient_id.in_(yours),
    )
    # Only the lines of recipes using something you have: scoring every line
    # in the catalog and then dropping the recipes with none took most of a
    # search's time.
    candidates = select(IngredientOption.recipe_id).where(IngredientOption.ingredient_id.in_(yours))
    per_line = (
        select(
            RecipeIngredient.recipe_id.label("recipe_id"),
            case((covered, 1), else_=0).label("covered"),
        )
        .where(RecipeIngredient.recipe_id.in_(candidates))
        .subquery()
    )
    tally = (
        select(
            per_line.c.recipe_id,
            func.sum(per_line.c.covered).label("have"),
            func.count().label("lines"),
        )
        .group_by(per_line.c.recipe_id)
        .having(func.sum(per_line.c.covered) > 0)
        .subquery()
    )
    matching = (
        select(Recipe.id, Recipe.title, Source.id, Source.title, tally.c.have, tally.c.lines)
        .join(tally, tally.c.recipe_id == Recipe.id)
        .join(used, used.c.recipe_id == Recipe.id)
        .join(Source, Source.id == Recipe.source_id)
        .where(*conditions)
    )
    if missing_max is not None:
        matching = matching.where(tally.c.lines - tally.c.have <= missing_max)
    total = await session.scalar(select(func.count()).select_from(matching.subquery()))
    first, closest = (), [func.lower(Source.title), func.lower(Recipe.title)]
    if by_rating or title:
        ratings = rated()
        matching = matching.outerjoin(ratings, ratings.c.recipe_id == Recipe.id)
        if by_rating:
            first = best_first(ratings)
        if title:
            closest = [
                *title_rank.order(*title, best_first(ratings)),
                func.lower(Recipe.title),
                func.lower(Source.title),
            ]
    rows = (
        await session.execute(
            matching.order_by(
                *first,
                used.c.used.desc(),
                # True division: SQLAlchemy makes / between integers a real one.
                (tally.c.have / tally.c.lines).desc(),
                (tally.c.lines - tally.c.have).asc(),
                tally.c.have.desc(),
                *closest,
                Recipe.id,
            )
            .offset(offset)
            # Read at call time, so a test can shrink it.
            .limit(PAGE)
        )
    ).all()
    listed = await with_pages(session, [r[:4] for r in rows])
    needs: dict[uuid.UUID, list[str]] = {}
    if rows:
        for recipe_id, text in await session.execute(
            select(RecipeIngredient.recipe_id, RecipeIngredient.original_text)
            .where(RecipeIngredient.recipe_id.in_([r[0] for r in rows]), ~covered)
            .order_by(RecipeIngredient.recipe_id, RecipeIngredient.position)
        ):
            needs.setdefault(recipe_id, []).append(text)
    names = dict(
        (
            await session.execute(
                select(Ingredient.id, Ingredient.name).where(Ingredient.id.in_(have))
            )
        ).all()
    )
    using: dict[uuid.UUID, set[uuid.UUID]] = {}
    if rows:
        for recipe_id, root in await session.execute(
            select(IngredientOption.recipe_id, roots.c.root)
            .join(roots, roots.c.id == IngredientOption.ingredient_id)
            .where(IngredientOption.recipe_id.in_([r[0] for r in rows]))
            .distinct()
        ):
            using.setdefault(recipe_id, set()).add(root)
    hits = [
        Hit(
            **u.model_dump(),
            have=r[4],
            lines=r[5],
            needs=needs.get(u.id, []),
            uses=[names[i] for i in have if i in using.get(u.id, set())],
        )
        for u, r in zip(listed, rows, strict=True)
    ]
    return hits, total or 0
