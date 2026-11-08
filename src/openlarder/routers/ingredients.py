"""Canonical ingredients: the list, the recipes that use one, and fixing them.

Reading is public, like the rest of the catalog. The list is ordered by how
many recipes use each ingredient, so the ones worth checking come first,
and can be narrowed by name, or by another name, as someone types.
Renaming, merging and deleting are for admins.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, exists, func, select

from openlarder import ingredients, substitutions
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import (
    Ingredient,
    IngredientAlias,
    IngredientOption,
    Recipe,
    RecipePage,
    Substitution,
    Work,
)
from openlarder.routers.substitutions import SwapOut, swap_out

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


class AliasOut(BaseModel):
    id: uuid.UUID
    name: str


class Related(BaseModel):
    id: uuid.UUID
    name: str


class IngredientOut(BaseModel):
    id: uuid.UUID
    name: str
    # Other names lines are matched by: names it had, and ingredients merged in.
    aliases: list[AliasOut]
    # Broader and narrower: cheese above cheddar, aged cheddar below it.
    parent: Related | None
    children: list[Related]
    recipes: list[UsedBy]
    total: int
    # Recipes using it or anything under it, as search counts them.
    family_total: int
    # What can stand in for it.
    swaps: list[SwapOut]


def contains_pattern(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def recipes_where(
    session: Session, *conditions: ColumnElement[bool], offset: int
) -> tuple[list[UsedBy], int]:
    """A page of the recipes meeting the conditions, by book then title,
    with their pages, and how many there are in all."""
    total = await session.scalar(select(func.count()).select_from(Recipe).where(*conditions))
    rows = (
        await session.execute(
            select(Recipe.id, Recipe.title, Work.id, Work.title)
            .join(Work, Work.id == Recipe.work_id)
            .where(*conditions)
            .order_by(func.lower(Work.title), func.lower(Recipe.title), Recipe.id)
            .offset(offset)
            .limit(PAGE)
        )
    ).all()
    pages: dict[uuid.UUID, list[str]] = {}
    if rows:
        for recipe_id, page in await session.execute(
            select(RecipePage.recipe_id, RecipePage.page)
            .where(RecipePage.recipe_id.in_([r[0] for r in rows]), RecipePage.page.is_not(None))
            .order_by(RecipePage.page)
        ):
            pages.setdefault(recipe_id, []).append(page)
    recipes = [
        UsedBy(id=r, title=t, book_id=b, book_title=bt, pages=pages.get(r, []))
        for r, t, b, bt in rows
    ]
    return recipes, total or 0


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
        like = contains_pattern(" ".join(q.split()))
        query = query.where(
            Ingredient.name.ilike(like, escape="\\")
            | exists().where(
                IngredientAlias.ingredient_id == Ingredient.id,
                IngredientAlias.name.ilike(like, escape="\\"),
            )
        )
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
    recipes, total = await recipes_where(
        session,
        Recipe.id.in_(
            select(IngredientOption.recipe_id).where(
                IngredientOption.ingredient_id == ingredient_id
            )
        ),
        offset=offset,
    )
    aliases = await session.execute(
        select(IngredientAlias.id, IngredientAlias.name)
        .where(IngredientAlias.ingredient_id == ingredient_id)
        .order_by(func.lower(IngredientAlias.name))
    )
    parent = await session.get(Ingredient, ingredient.parent_id) if ingredient.parent_id else None
    children = await session.execute(
        select(Ingredient.id, Ingredient.name)
        .where(Ingredient.parent_id == ingredient_id)
        .order_by(func.lower(Ingredient.name))
    )
    children = [Related(id=i, name=n) for i, n in children]
    family_total = total
    if children:
        family_total = await session.scalar(
            select(func.count(func.distinct(IngredientOption.recipe_id))).where(
                IngredientOption.ingredient_id.in_(ingredients.family(ingredient_id))
            )
        )
    return IngredientOut(
        id=ingredient.id,
        name=ingredient.name,
        aliases=[AliasOut(id=a, name=n) for a, n in aliases],
        parent=Related(id=parent.id, name=parent.name) if parent else None,
        children=children,
        recipes=recipes,
        total=total,
        family_total=family_total or 0,
        swaps=[
            swap_out(s)
            for s in await substitutions.listed(
                session, Substitution.from_ingredient_id == ingredient_id
            )
        ],
    )


# Fixing the list


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MergeInto(BaseModel):
    into: uuid.UUID


class Named(BaseModel):
    id: uuid.UUID
    name: str


async def _ingredient_or_404(session: Session, ingredient_id: uuid.UUID) -> Ingredient:
    ingredient = await session.get(Ingredient, ingredient_id)
    if ingredient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such ingredient.")
    return ingredient


def _taken(exc: ingredients.Taken) -> HTTPException:
    # The other ingredient, so the page can offer to merge into it.
    other = exc.ingredient
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "message": f"“{other.name}” is already an ingredient, or another name for one.",
            "ingredient": {"id": str(other.id), "name": other.name},
        },
    )


@router.patch("/{ingredient_id}", response_model=Named, dependencies=[SameOrigin])
async def rename_ingredient(
    ingredient_id: uuid.UUID, body: Rename, admin: AdminUser, session: Session
) -> Named:
    ingredient = await _ingredient_or_404(session, ingredient_id)
    try:
        await ingredients.rename(session, ingredient, body.name)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except ingredients.Taken as exc:
        raise _taken(exc) from None
    await session.commit()
    return Named(id=ingredient.id, name=ingredient.name)


@router.post("/{ingredient_id}/merge", response_model=Named, dependencies=[SameOrigin])
async def merge_ingredient(
    ingredient_id: uuid.UUID, body: MergeInto, admin: AdminUser, session: Session
) -> Named:
    """Merge this ingredient into another; answers with the one that's left."""
    source = await _ingredient_or_404(session, ingredient_id)
    target = await _ingredient_or_404(session, body.into)
    try:
        await ingredients.merge(session, source, target)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await session.commit()
    return Named(id=target.id, name=target.name)


@router.delete(
    "/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SameOrigin]
)
async def delete_ingredient(
    ingredient_id: uuid.UUID, admin: AdminUser, session: Session
) -> Response:
    ingredient = await _ingredient_or_404(session, ingredient_id)
    try:
        await ingredients.remove(session, ingredient)
    except ingredients.InUse:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Something still uses this ingredient. Merge it into another instead.",
        ) from None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{ingredient_id}/aliases/{alias_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SameOrigin],
)
async def delete_alias(
    ingredient_id: uuid.UUID, alias_id: uuid.UUID, admin: AdminUser, session: Session
) -> Response:
    """Stop matching lines by this name. Lines already matched keep their
    ingredient; new ones written this way become an ingredient of their own."""
    alias = await session.get(IngredientAlias, alias_id)
    if alias is None or alias.ingredient_id != ingredient_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such name for this ingredient.")
    await session.delete(alias)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ParentIn(BaseModel):
    # None: under nothing.
    parent: uuid.UUID | None


@router.put("/{ingredient_id}/parent", response_model=Named, dependencies=[SameOrigin])
async def set_parent(
    ingredient_id: uuid.UUID, body: ParentIn, admin: AdminUser, session: Session
) -> Named:
    """Put this ingredient under another, or under nothing; answers with
    the ingredient."""
    ingredient = await _ingredient_or_404(session, ingredient_id)
    parent = await _ingredient_or_404(session, body.parent) if body.parent else None
    try:
        await ingredients.set_parent(session, ingredient, parent)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await session.commit()
    return Named(id=ingredient.id, name=ingredient.name)
