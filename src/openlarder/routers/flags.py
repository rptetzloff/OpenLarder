"""Flagged recipes: listing flags, and dealing with them.

Admins see every flag; anyone signed in sees the flags on recipes they
added. Dealing with a flag is marking it fixed, after changing the recipe,
or dismissing it as wrong, with a reason; either records who and when, so
review can take the history over. Only an admin or whoever added the recipe
may deal with its flags. *Ray, 2026-11-07.*
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from openlarder import visibility
from openlarder.auth import CurrentUser, SameOrigin
from openlarder.db import Session
from openlarder.models import FlagKind, Recipe, RecipeFlag, Source, User

router = APIRouter(tags=["flags"])
PAGE = 50


class RecipeRef(BaseModel):
    id: uuid.UUID
    title: str
    source_id: uuid.UUID
    source_title: str


class FlagOut(BaseModel):
    id: uuid.UUID
    kind: str
    detail: str | None
    created_at: datetime
    resolved_at: datetime | None
    resolution: str | None
    note: str | None
    recipe: RecipeRef


class FlagPage(BaseModel):
    flags: list[FlagOut]
    # Open flags in this view, by kind, for the filter's counts.
    open_by_kind: dict[str, int]
    total: int


class Resolve(BaseModel):
    resolution: Literal["fixed", "dismissed"]
    note: str | None = Field(default=None, max_length=500)


def _visible(user: User, scope: str):
    """The recipes whose flags this person may see in this view."""
    if scope == "all":
        if not user.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can see every flag.")
        return None
    return Recipe.created_by == user.id


def _out(flag: RecipeFlag, recipe: Recipe, book: Source) -> FlagOut:
    return FlagOut(
        id=flag.id,
        kind=flag.kind,
        detail=flag.detail,
        created_at=flag.created_at,
        resolved_at=flag.resolved_at,
        resolution=flag.resolution,
        note=flag.note,
        recipe=RecipeRef(
            id=recipe.id, title=recipe.title, source_id=book.id, source_title=book.title
        ),
    )


@router.get("/api/flags", response_model=FlagPage)
async def list_flags(
    user: CurrentUser,
    session: Session,
    scope: Literal["all", "mine"] = "mine",
    state: Literal["open", "dealt_with"] = "open",
    kind: FlagKind | None = None,
    offset: int = Query(0, ge=0),
) -> FlagPage:
    mine = _visible(user, scope)
    base = (
        select(RecipeFlag, Recipe, Source)
        .join(Recipe, Recipe.id == RecipeFlag.recipe_id)
        .join(Source, Source.id == Recipe.source_id)
        .where(visibility.recipes_seen_by(user))
    )
    if mine is not None:
        base = base.where(mine)
    counts_query = (
        select(RecipeFlag.kind, func.count())
        .join(Recipe, Recipe.id == RecipeFlag.recipe_id)
        .where(RecipeFlag.resolved_at.is_(None), visibility.recipes_seen_by(user))
        .group_by(RecipeFlag.kind)
    )
    if mine is not None:
        counts_query = counts_query.where(mine)
    open_by_kind = dict((await session.execute(counts_query)).all())

    filtered = base.where(
        RecipeFlag.resolved_at.is_(None) if state == "open" else RecipeFlag.resolved_at.is_not(None)
    )
    if kind is not None:
        filtered = filtered.where(RecipeFlag.kind == kind.value)
    total = await session.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    rows = (
        await session.execute(
            filtered.order_by(Source.title, Recipe.title, RecipeFlag.created_at)
            .offset(offset)
            .limit(PAGE)
        )
    ).all()
    return FlagPage(
        flags=[_out(f, r, w) for f, r, w in rows], open_by_kind=open_by_kind, total=total
    )


@router.get("/api/recipes/{recipe_id}/flags", response_model=list[FlagOut])
async def recipe_flags(recipe_id: uuid.UUID, user: CurrentUser, session: Session) -> list[FlagOut]:
    """A recipe's flags, open first, for whoever may deal with them; others see none."""
    recipe = await session.get(Recipe, recipe_id)
    if recipe is None or not await visibility.can_see(
        session, user, await session.get_one(Source, recipe.source_id)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe.")
    if not (user.is_admin or recipe.created_by == user.id):
        return []
    book = await session.get(Source, recipe.source_id)
    flags = (
        await session.scalars(
            select(RecipeFlag)
            .where(RecipeFlag.recipe_id == recipe_id)
            .order_by(RecipeFlag.resolved_at.nulls_first(), RecipeFlag.created_at)
        )
    ).all()
    return [_out(f, recipe, book) for f in flags]


@router.post("/api/flags/{flag_id}/resolve", response_model=FlagOut, dependencies=[SameOrigin])
async def resolve(
    flag_id: uuid.UUID, body: Resolve, user: CurrentUser, session: Session
) -> FlagOut:
    flag = await session.get(RecipeFlag, flag_id)
    recipe = await session.get(Recipe, flag.recipe_id) if flag else None
    if recipe is None or not await visibility.can_see(
        session, user, await session.get_one(Source, recipe.source_id)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such flag.")
    if not (user.is_admin or recipe.created_by == user.id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only an admin or whoever added the recipe can do that."
        )
    if flag.resolved_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That flag has already been dealt with.")
    note = " ".join((body.note or "").split()) or None
    if body.resolution == "dismissed" and not note:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Say why the flag is wrong, so it can be checked.",
        )
    flag.resolution = body.resolution
    flag.note = note
    flag.resolved_by = user.id
    flag.resolved_at = func.now()
    await session.commit()
    await session.refresh(flag)
    return _out(flag, recipe, await session.get(Source, recipe.source_id))
