"""Ratings: one to five spoons on a recipe (migration 0068). *Ray,
2026-11-11: "star ratings or similar... spoons or forks or salamanders".*

Anyone signed in rates a recipe they can see, once, and changes or clears
it at will. Everyone who can see the recipe sees its average and how many
gave it; nobody sees who gave what. Listings carry the same two numbers
(routers/ingredients.py, with_pages). No words go with a rating, so there
is nothing to moderate.

Ratings rank, too (*Ray, 2026-11-12*). A source's page and an author's
show their top rated recipes: those averaging four spoons or more, the
best five, the higher average first and, level, the one more people
rated. With none, the section is left off, not filled with some other
ranking (SCOPING.md). A search can be sorted the same way: rated recipes
first, then the rest as they'd come anyway. One person's five spoons tops
a list for now; a least number of ratings would show nothing at all while
the site is new, and is a constant to add here when it isn't.
"""

import uuid

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from openlarder import visibility
from openlarder.auth import CurrentUser, SameOrigin, Viewer
from openlarder.db import Session
from openlarder.models import Recipe, RecipeRating, Source
from openlarder.routers.ingredients import UsedBy, with_pages

router = APIRouter(tags=["ratings"])


class Rating(BaseModel):
    # The average, to one decimal place; none until someone rates it.
    spoons: float | None
    ratings: int
    # Yours, signed in and having rated it.
    mine: int | None = None


class RatingIn(BaseModel):
    spoons: int = Field(ge=1, le=5)


async def averages(session, recipe_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[float, int]]:
    """Each rated recipe's average, to one decimal place, and how many
    rated it."""
    if not recipe_ids:
        return {}
    rows = await session.execute(
        select(RecipeRating.recipe_id, func.avg(RecipeRating.spoons), func.count())
        .where(RecipeRating.recipe_id.in_(recipe_ids))
        .group_by(RecipeRating.recipe_id)
    )
    return {r: (round(float(avg), 1), n) for r, avg, n in rows}


# Top rated: this average or more, as it's shown (to one decimal place),
# and this many of them.
TOP_SPOONS = 4
TOP_SHOWN = 5


def rated():
    """Each rated recipe's average, as it's shown, and how many rated it:
    to join recipes to, and order them by."""
    return (
        select(
            RecipeRating.recipe_id.label("recipe_id"),
            func.round(func.avg(RecipeRating.spoons), 1).label("spoons"),
            func.count().label("ratings"),
        )
        .group_by(RecipeRating.recipe_id)
        .subquery("rated")
    )


def best_first(ratings) -> tuple:
    """The order ratings put recipes in: the higher average first, then the
    one more people rated; unrated ones after them all."""
    return (ratings.c.spoons.desc().nulls_last(), ratings.c.ratings.desc().nulls_last())


async def top_rated(session, *conditions) -> list[UsedBy]:
    """The top rated of the recipes meeting the conditions, best first."""
    ratings = rated()
    rows = (
        await session.execute(
            select(Recipe.id, Recipe.title, Source.id, Source.title)
            .join(Source, Source.id == Recipe.source_id)
            .join(ratings, ratings.c.recipe_id == Recipe.id)
            .where(*conditions, ratings.c.spoons >= TOP_SPOONS)
            .order_by(*best_first(ratings), func.lower(Recipe.title), Recipe.id)
            .limit(TOP_SHOWN)
        )
    ).all()
    return await with_pages(session, rows)


async def _seen(session, viewer, recipe_id: uuid.UUID) -> None:
    seen = await session.scalar(
        select(Recipe.id).where(Recipe.id == recipe_id, visibility.recipes_seen_by(viewer))
    )
    if seen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe.")


async def _rating(session, viewer, recipe_id: uuid.UUID) -> Rating:
    spoons, count = (await averages(session, [recipe_id])).get(recipe_id, (None, 0))
    mine = None
    if viewer is not None:
        mine = await session.scalar(
            select(RecipeRating.spoons).where(
                RecipeRating.user_id == viewer.id, RecipeRating.recipe_id == recipe_id
            )
        )
    return Rating(spoons=spoons, ratings=count, mine=mine)


@router.get("/api/recipes/{recipe_id}/rating", response_model=Rating)
async def get_rating(recipe_id: uuid.UUID, session: Session, viewer: Viewer) -> Rating:
    """A recipe's average and how many rated it, and yours when signed in."""
    await _seen(session, viewer, recipe_id)
    return await _rating(session, viewer, recipe_id)


@router.put("/api/recipes/{recipe_id}/rating", response_model=Rating, dependencies=[SameOrigin])
async def rate(recipe_id: uuid.UUID, body: RatingIn, user: CurrentUser, session: Session) -> Rating:
    """Give a recipe one to five spoons, or change what you gave."""
    await _seen(session, user, recipe_id)
    row = await session.get(RecipeRating, (user.id, recipe_id))
    if row is None:
        row = RecipeRating(user_id=user.id, recipe_id=recipe_id)
        session.add(row)
    row.spoons = body.spoons
    await session.commit()
    return await _rating(session, user, recipe_id)


@router.delete("/api/recipes/{recipe_id}/rating", status_code=204, dependencies=[SameOrigin])
async def unrate(recipe_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    await session.execute(
        delete(RecipeRating).where(
            RecipeRating.user_id == user.id, RecipeRating.recipe_id == recipe_id
        )
    )
    await session.commit()
    return Response(status_code=204)
