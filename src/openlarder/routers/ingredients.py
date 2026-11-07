"""Canonical ingredients: the list, and the recipes that use one.

Public, like the rest of the catalog. The list is ordered by how many
recipes use each ingredient, so the ones worth checking come first, and
can be narrowed by name as someone types.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from openlarder.db import Session
from openlarder.models import Ingredient, IngredientOption, Recipe, RecipePage, Work

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])

PAGE = 100


class IngredientSummary(BaseModel):
    id: uuid.UUID
    name: str
    recipes: int


class IngredientList(BaseModel):
    ingredients: list[IngredientSummary]
    total: int


class UsedBy(BaseModel):
    id: uuid.UUID
    title: str
    book_id: uuid.UUID
    book_title: str
    pages: list[str]


class IngredientOut(BaseModel):
    id: uuid.UUID
    name: str
    recipes: list[UsedBy]
    total: int


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("", response_model=IngredientList)
async def list_ingredients(
    session: Session, q: str = "", offset: int = Query(0, ge=0)
) -> IngredientList:
    uses = (
        select(
            IngredientOption.ingredient_id,
            func.count(func.distinct(IngredientOption.recipe_id)).label("n"),
        )
        .where(IngredientOption.ingredient_id.is_not(None))
        .group_by(IngredientOption.ingredient_id)
        .subquery()
    )
    query = select(Ingredient.id, Ingredient.name, func.coalesce(uses.c.n, 0)).outerjoin(
        uses, uses.c.ingredient_id == Ingredient.id
    )
    if q.strip():
        query = query.where(Ingredient.name.ilike(_like(" ".join(q.split())), escape="\\"))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(func.coalesce(uses.c.n, 0).desc(), func.lower(Ingredient.name))
        .offset(offset)
        .limit(PAGE)
    )
    return IngredientList(
        ingredients=[IngredientSummary(id=i, name=n, recipes=c) for i, n, c in rows],
        total=total or 0,
    )


@router.get("/{ingredient_id}", response_model=IngredientOut)
async def get_ingredient(
    ingredient_id: uuid.UUID, session: Session, offset: int = Query(0, ge=0)
) -> IngredientOut:
    ingredient = await session.get(Ingredient, ingredient_id)
    if ingredient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such ingredient.")
    using = select(IngredientOption.recipe_id).where(
        IngredientOption.ingredient_id == ingredient_id
    )
    total = await session.scalar(
        select(func.count(func.distinct(IngredientOption.recipe_id))).where(
            IngredientOption.ingredient_id == ingredient_id
        )
    )
    recipes = (
        await session.execute(
            select(Recipe.id, Recipe.title, Work.id, Work.title)
            .join(Work, Work.id == Recipe.work_id)
            .where(Recipe.id.in_(using))
            .order_by(func.lower(Work.title), func.lower(Recipe.title), Recipe.id)
            .offset(offset)
            .limit(PAGE)
        )
    ).all()
    pages: dict[uuid.UUID, list[str]] = {}
    if recipes:
        for recipe_id, page in await session.execute(
            select(RecipePage.recipe_id, RecipePage.page)
            .where(RecipePage.recipe_id.in_([r[0] for r in recipes]), RecipePage.page.is_not(None))
            .order_by(RecipePage.page)
        ):
            pages.setdefault(recipe_id, []).append(page)
    return IngredientOut(
        id=ingredient.id,
        name=ingredient.name,
        recipes=[
            UsedBy(id=r, title=t, book_id=b, book_title=bt, pages=pages.get(r, []))
            for r, t, b, bt in recipes
        ],
        total=total or 0,
    )
