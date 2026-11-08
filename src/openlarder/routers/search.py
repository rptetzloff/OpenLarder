"""Search: the recipes that use every one of several ingredients, or whose
titles have every word typed, or both, in every book or in one.

Public, like the rest of the catalog. A recipe matches an ingredient when
any option on any of its lines is that ingredient or one under it in the
hierarchy, so a search for cheese finds a recipe that uses cheddar, and
"butter or oil" counts for butter. An ingredient's own page lists exactly
the recipes matched to it; this is the broader search.

An ingredient ID that no longer exists, as after a merge, is left out of
the search and reported, so an old link still finds what it can.

Title words match anywhere in a title, ignoring case, so "rhubarb cake"
finds "Rhubarb and Ginger Cake"; accents count, as they do for
ingredients. The trigram index on recipe titles serves these.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from openlarder.db import Session
from openlarder.ingredients import family
from openlarder.models import Ingredient, IngredientOption, Recipe, Work
from openlarder.routers.ingredients import UsedBy, contains_pattern, recipes_where

router = APIRouter(prefix="/api/search", tags=["search"])

MAX_INGREDIENTS = 10
MAX_WORDS = 10


class Named(BaseModel):
    id: uuid.UUID
    name: str


class Found(BaseModel):
    # The book searched within, if one was.
    book: Named | None
    # The ingredients searched for, in the order asked, and any IDs that
    # name no ingredient now.
    ingredients: list[Named]
    missing: list[uuid.UUID]
    # The title words searched for, tidied.
    q: str
    recipes: list[UsedBy]
    total: int


@router.get("", response_model=Found)
async def search(
    session: Session,
    ingredient: Annotated[list[uuid.UUID] | None, Query()] = None,
    q: str = Query("", max_length=200),
    book: uuid.UUID | None = None,
    offset: int = Query(0, ge=0),
) -> Found:
    asked = list(dict.fromkeys(ingredient or []))
    words = list(dict.fromkeys(q.casefold().split()))
    if not asked and not words:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose an ingredient or type part of a title."
        )
    if len(words) > MAX_WORDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Use at most {MAX_WORDS} words of a title."
        )
    if len(asked) > MAX_INGREDIENTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Search for at most {MAX_INGREDIENTS} ingredients at once.",
        )
    rows = await session.execute(
        select(Ingredient.id, Ingredient.name).where(Ingredient.id.in_(asked))
    )
    names = {i: name for i, name in rows}
    known = [i for i in asked if i in names]
    work = await session.get(Work, book) if book else None
    if book and work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    found = Found(
        book=Named(id=work.id, name=work.title) if work else None,
        ingredients=[Named(id=i, name=names[i]) for i in known],
        missing=[i for i in asked if i not in names],
        q=" ".join(q.split()),
        recipes=[],
        total=0,
    )
    # Every ingredient asked for is gone: nothing left to search by.
    if not known and not words:
        return found
    conditions = [
        Recipe.id.in_(
            select(IngredientOption.recipe_id).where(
                IngredientOption.ingredient_id.in_(family(i, f"family_{n}"))
            )
        )
        for n, i in enumerate(known)
    ]
    conditions += [Recipe.title.ilike(contains_pattern(w), escape="\\") for w in words]
    if work:
        conditions.append(Recipe.work_id == work.id)
    found.recipes, found.total = await recipes_where(session, *conditions, offset=offset)
    return found
