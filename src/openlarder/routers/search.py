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

**Title words** must all appear in the title, ignoring case; accents count,
as they do for ingredients. The trigram index on recipe titles serves them.

**Sources**: a recipe in any of them. IDs that name no ingredient or source now,
as after a merge, are left out of the search and reported, so an old link
still finds what it can. An ingredient's own page lists exactly the recipes
matched to it; this is the broader search.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import aliased

from openlarder import visibility
from openlarder.auth import Viewer
from openlarder.db import Session
from openlarder.ingredients import family, rooted_family
from openlarder.models import Ingredient, IngredientOption, Recipe, RecipeIngredient, Source
from openlarder.routers.ingredients import (
    UsedBy,
    contains_pattern,
    recipes_where,
    with_pages,
)

router = APIRouter(prefix="/api/search", tags=["search"])

MAX_INGREDIENTS = 30
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
    # The title words searched for, tidied.
    q: str
    recipes: list[Hit]
    total: int
    # Recipes a page holds, so a listing can number its pages.
    per_page: int = 0


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
    offset: int = Query(0, ge=0),
) -> Found:
    asked = list(dict.fromkeys(ingredient or []))
    unwanted = list(dict.fromkeys(without or []))
    words = list(dict.fromkeys(q.casefold().split()))
    shelf = list(dict.fromkeys(source or []))
    if not asked and not words:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose an ingredient or type part of a title."
        )
    _too_many(len(asked), MAX_INGREDIENTS, "ingredients")
    _too_many(len(words), MAX_WORDS, "words of a title")
    _too_many(len(shelf), MAX_SOURCES, "sources")
    _too_many(len(unwanted), MAX_INGREDIENTS, "ingredients to leave out")

    found_names = await session.execute(
        select(Ingredient.id, Ingredient.name).where(
            Ingredient.id.in_(asked + unwanted), visibility.ingredients_seen_by(viewer)
        )
    )
    names = {i: n for i, n in found_names}
    found_titles = await session.execute(
        select(Source.id, Source.title).where(
            Source.id.in_(shelf), visibility.sources_seen_by(viewer)
        )
    )
    titles = {i: t for i, t in found_titles}
    known = [i for i in asked if i in names]
    books = [i for i in shelf if i in titles]
    found = Found(
        sources=[Named(id=i, name=titles[i]) for i in books],
        ingredients=[Named(id=i, name=names[i]) for i in known],
        without=[Named(id=i, name=names[i]) for i in unwanted if i in names],
        missing=[i for i in asked + unwanted if i not in names],
        missing_sources=[i for i in shelf if i not in titles],
        q=" ".join(q.split()),
        recipes=[],
        total=0,
        # Read at call time, so a test can shrink it.
        per_page=PAGE,
    )
    # Every ingredient asked for is gone: nothing left to search by.
    if not known and not words:
        return found
    conditions = [Recipe.title.ilike(contains_pattern(w), escape="\\") for w in words]
    conditions.append(visibility.recipes_seen_by(viewer))
    if kind:
        conditions.append(Recipe.source_id.in_(select(Source.id).where(Source.kind.in_(kind))))
    if books:
        conditions.append(Recipe.source_id.in_(books))
    left_out = [i for i in unwanted if i in names]
    if left_out:
        conditions.append(~_needs_any(left_out))
    if not known:
        page, found.total = await recipes_where(session, *conditions, offset=offset, limit=PAGE)
        found.recipes = [Hit(**r.model_dump()) for r in page]
        return found
    found.recipes, found.total = await _best_match(session, known, conditions, offset)
    return found


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


async def _best_match(session: Session, have: list[uuid.UUID], conditions, offset: int):
    """Recipes covering any line with what you have, by the share of lines
    covered (so complete ones come first), then fewest still needed, most of
    yours used, then book and title."""
    yours = family(*have, name="yours")
    # Which of yours each match is under, to say which a recipe uses.
    roots = rooted_family(*have, name="yours_by_root")
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
        .join(Source, Source.id == Recipe.source_id)
        .where(*conditions)
    )
    total = await session.scalar(select(func.count()).select_from(matching.subquery()))
    rows = (
        await session.execute(
            matching.order_by(
                # True division: SQLAlchemy makes / between integers a real one.
                (tally.c.have / tally.c.lines).desc(),
                (tally.c.lines - tally.c.have).asc(),
                tally.c.have.desc(),
                func.lower(Source.title),
                func.lower(Recipe.title),
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
