"""Recipe entries: read one, and add, change or remove one (admins only).

Reading is public. Writing is for admins until review exists, like books.
"""

import uuid

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from openlarder import recipes
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import Edition, Recipe, RecipeIngredient, RecipePage, Work

router = APIRouter(tags=["recipes"])


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


class BookRef(BaseModel):
    id: uuid.UUID
    title: str


class RecipeOut(BaseModel):
    id: uuid.UUID
    title: str
    book: BookRef
    pages: list[PageOut]
    ingredients: list[str]


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
    work = await session.get(Work, recipe.work_id)
    pages = (
        await session.execute(
            select(RecipePage.page, Edition)
            .join(Edition, Edition.id == RecipePage.edition_id)
            .where(RecipePage.recipe_id == recipe.id)
            .order_by(Edition.published_year.desc().nulls_last(), Edition.isbn13)
        )
    ).all()
    lines = (
        await session.scalars(
            select(RecipeIngredient.original_text)
            .where(RecipeIngredient.recipe_id == recipe.id)
            .order_by(RecipeIngredient.position)
        )
    ).all()
    return RecipeOut(
        id=recipe.id,
        title=recipe.title,
        book=BookRef(id=work.id, title=work.title),
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
        ingredients=list(lines),
    )


@router.get("/api/recipes/{recipe_id}", response_model=RecipeOut)
async def get_recipe(recipe_id: uuid.UUID, session: Session) -> RecipeOut:
    return await _out(session, await _recipe_or_404(session, recipe_id))


@router.post(
    "/api/books/{work_id}/recipes",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def add_recipe(
    work_id: uuid.UUID, body: RecipeIn, admin: AdminUser, session: Session
) -> Created:
    if await session.get(Work, work_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    entry = _clean(body)
    try:
        recipe = await recipes.create(session, work_id, entry)
    except recipes.InvalidRecipe as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
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
    await session.commit()
    return await _out(session, recipe)


@router.delete(
    "/api/recipes/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SameOrigin],
)
async def remove_recipe(recipe_id: uuid.UUID, admin: AdminUser, session: Session) -> Response:
    recipe = await _recipe_or_404(session, recipe_id)
    await session.delete(recipe)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
