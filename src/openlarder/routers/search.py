"""Search: the recipes that use every one of several ingredients.

Public, like the rest of the catalog. A recipe matches an ingredient when
any option on any of its lines is that ingredient or one under it in the
hierarchy, so a search for cheese finds a recipe that uses cheddar, and
"butter or oil" counts for butter. An ingredient's own page lists exactly
the recipes matched to it; this is the broader search.

An ingredient ID that no longer exists, as after a merge, is left out of
the search and reported, so an old link still finds what it can.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from openlarder.db import Session
from openlarder.models import Ingredient, IngredientOption, Recipe
from openlarder.routers.ingredients import UsedBy, recipes_where

router = APIRouter(prefix="/api/search", tags=["search"])

MAX_INGREDIENTS = 10


class Named(BaseModel):
    id: uuid.UUID
    name: str


class Found(BaseModel):
    # The ingredients searched for, in the order asked, and any IDs that
    # name no ingredient now.
    ingredients: list[Named]
    missing: list[uuid.UUID]
    recipes: list[UsedBy]
    total: int


def _family(ingredient_id: uuid.UUID, n: int):
    """The ingredient and everything under it. UNION, not UNION ALL, so a
    loop in the hierarchy, which isn't prevented, still ends."""
    tree = (
        select(Ingredient.id)
        .where(Ingredient.id == ingredient_id)
        .cte(name=f"family_{n}", recursive=True)
    )
    tree = tree.union(select(Ingredient.id).where(Ingredient.parent_id == tree.c.id))
    return select(tree.c.id)


@router.get("", response_model=Found)
async def search(
    session: Session,
    ingredient: Annotated[list[uuid.UUID] | None, Query()] = None,
    offset: int = Query(0, ge=0),
) -> Found:
    asked = list(dict.fromkeys(ingredient or []))
    if not asked:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose an ingredient.")
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
    found = Found(
        ingredients=[Named(id=i, name=names[i]) for i in known],
        missing=[i for i in asked if i not in names],
        recipes=[],
        total=0,
    )
    if not known:
        return found
    conditions = [
        Recipe.id.in_(
            select(IngredientOption.recipe_id).where(
                IngredientOption.ingredient_id.in_(_family(i, n))
            )
        )
        for n, i in enumerate(known)
    ]
    found.recipes, found.total = await recipes_where(session, *conditions, offset=offset)
    return found
