"""Recipe entries: read one, and add, change or remove one (admins only).

An entry is where a recipe is and what goes in it, never how much or how;
see recipes.py.

Reading is public. Writing is for admins until review exists, like books.
"""

import uuid

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from openlarder import detector, recipes, references, substitutions
from openlarder import lines as line_reading
from openlarder.auth import AdminUser, CurrentUser, SameOrigin
from openlarder.db import Session
from openlarder.models import (
    Edition,
    Ingredient,
    IngredientOption,
    Recipe,
    RecipeIngredient,
    RecipeLocation,
    Source,
)
from openlarder.routers.substitutions import SwapOut, swap_out

router = APIRouter(tags=["recipes"])


class LinesIn(BaseModel):
    # Blank lines count here, though saving drops them.
    lines: list[str] = Field(max_length=2 * recipes.MAX_LINES)


class LineReview(BaseModel):
    problems: list[str]
    suggestion: str | None
    remove: bool


class LinesReviewed(BaseModel):
    lines: list[LineReview]


@router.post("/api/ingredient-lines/check", response_model=LinesReviewed, dependencies=[SameOrigin])
async def check_lines(body: LinesIn, user: CurrentUser) -> LinesReviewed:
    """What the entry rules say about each line, for the form to show as
    it's typed. Changes nothing; saving doesn't depend on it."""
    return LinesReviewed(
        lines=[
            LineReview(problems=r.problems, suggestion=r.suggestion, remove=r.remove)
            for r in detector.review_all([line[: recipes.MAX_LINE] for line in body.lines])
        ]
    )


class PageIn(BaseModel):
    edition_id: uuid.UUID
    page: str | None = None


class RecipeIn(BaseModel):
    title: str
    editions: list[PageIn]
    ingredients: list[str] = []


class PageOut(BaseModel):
    edition_id: uuid.UUID
    edition_title: str | None
    isbn13: str | None
    published_year: int | None
    page: str | None


class SourceRef(BaseModel):
    id: uuid.UUID
    title: str


class RecipeLink(BaseModel):
    id: uuid.UUID
    title: str


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
    source: SourceRef
    pages: list[PageOut]
    # The lines as typed, which is what the edit form edits.
    ingredients: list[str]
    # The same lines read into their options, with page references linked.
    lines: list[LineOut]
    # Recipes in the book that use this one as a component.
    used_in: list[RecipeLink]
    # What can stand in for its ingredients, the recipes it cites, or itself.
    swaps: list[SwapOut]


class Created(BaseModel):
    id: uuid.UUID


def _clean(body: RecipeIn) -> recipes.RecipeEntry:
    try:
        return recipes.clean(
            body.title, [(p.edition_id, p.page) for p in body.editions], body.ingredients
        )
    except recipes.InvalidRecipe as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


async def _recipe_or_404(session, recipe_id: uuid.UUID) -> Recipe:
    recipe = await session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe.")
    return recipe


async def _out(session, recipe: Recipe) -> RecipeOut:
    work = await session.get(Source, recipe.source_id)
    pages = (
        await session.execute(
            select(RecipeLocation.page, Edition)
            .join(Edition, Edition.id == RecipeLocation.edition_id)
            .where(RecipeLocation.recipe_id == recipe.id)
            .order_by(Edition.published_year.desc().nulls_last(), Edition.isbn13)
        )
    ).all()
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
    return RecipeOut(
        id=recipe.id,
        title=recipe.title,
        source=SourceRef(id=work.id, title=work.title),
        pages=[
            PageOut(
                edition_id=e.id,
                edition_title=e.title,
                isbn13=e.isbn13,
                published_year=e.published_year,
                page=page,
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
        used_in=[RecipeLink(id=i, title=t) for i, t in used_in],
        swaps=[
            swap_out(x)
            for x in await substitutions.listed(session, substitutions.for_recipe(recipe.id))
        ],
    )


@router.get("/api/recipes/{recipe_id}", response_model=RecipeOut)
async def get_recipe(recipe_id: uuid.UUID, session: Session) -> RecipeOut:
    return await _out(session, await _recipe_or_404(session, recipe_id))


@router.post(
    "/api/sources/{source_id}/recipes",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def add_recipe(
    source_id: uuid.UUID, body: RecipeIn, admin: AdminUser, session: Session
) -> Created:
    if await session.get(Source, source_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    entry = _clean(body)
    try:
        recipe = await recipes.create(session, source_id, entry)
    except recipes.InvalidRecipe as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await references.relink(session, source_id)
    await session.commit()
    return Created(id=recipe.id)


@router.put("/api/recipes/{recipe_id}", response_model=RecipeOut, dependencies=[SameOrigin])
async def change_recipe(
    recipe_id: uuid.UUID, body: RecipeIn, admin: AdminUser, session: Session
) -> RecipeOut:
    recipe = await _recipe_or_404(session, recipe_id)
    entry = _clean(body)
    try:
        await recipes.replace(session, recipe, entry)
    except recipes.InvalidRecipe as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await references.relink(session, recipe.source_id)
    await session.commit()
    return await _out(session, recipe)


@router.delete(
    "/api/recipes/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SameOrigin],
)
async def remove_recipe(recipe_id: uuid.UUID, admin: AdminUser, session: Session) -> Response:
    recipe = await _recipe_or_404(session, recipe_id)
    source_id = recipe.source_id
    await references.release(session, recipe.id)
    await session.delete(recipe)
    await session.flush()
    await references.relink(session, source_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
