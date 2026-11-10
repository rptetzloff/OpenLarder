"""Tags: course, cuisine, diet and technique, on sources and recipes.

Tags come from a fixed list per kind, which only admins add to (migration
0032 starts it). A source's tags are its recipes' too: a gluten-free book
tags every recipe in it. Whoever may change a source's recipes may tag the
source and its recipes (visibility.may_edit): admins, and for a family
collection its owner and its group's editors. *Ray, 2026-11-09.*
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.auth import CurrentUser, ModeratorUser, SameOrigin
from openlarder.db import Session
from openlarder.models import RecipeTag, Source, SourceTag, Tag, TagKind
from openlarder.routers.recipes import _editable_source, _recipe_or_404
from openlarder.tagging import (
    MAX_TAGS,
    RecipeTagOut,
    TagOut,
    order,
    recipe_tags,
    source_tags,
    tag_out,
)

router = APIRouter(tags=["tags"])


@router.get("/api/tags", response_model=list[TagOut])
async def list_tags(session: Session) -> list[TagOut]:
    """Every tag, diet first, then course, cuisine and technique, A to Z."""
    return [tag_out(t) for t in await session.scalars(select(Tag).order_by(*order()))]


class NewTag(BaseModel):
    kind: TagKind
    name: str = Field(max_length=60)


@router.post(
    "/api/tags",
    response_model=TagOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def add_tag(body: NewTag, admin: ModeratorUser, session: Session) -> TagOut:
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the tag a name.")
    taken = await session.scalar(
        select(Tag).where(Tag.kind == body.kind, func.lower(Tag.name) == name.lower())
    )
    if taken is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"“{taken.name}” is a tag already.")
    tag = Tag(kind=body.kind, name=name)
    session.add(tag)
    await session.commit()
    return tag_out(tag)


class TagsIn(BaseModel):
    tags: list[uuid.UUID] = Field(default=[], max_length=MAX_TAGS)


async def _known(session: AsyncSession, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    wanted = list(dict.fromkeys(ids))
    found = set(await session.scalars(select(Tag.id).where(Tag.id.in_(wanted))))
    if missing := [i for i in wanted if i not in found]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No such tag: {missing[0]}.")
    return wanted


@router.put(
    "/api/recipes/{recipe_id}/tags", response_model=list[RecipeTagOut], dependencies=[SameOrigin]
)
async def set_recipe_tags(
    recipe_id: uuid.UUID, body: TagsIn, user: CurrentUser, session: Session
) -> list[RecipeTagOut]:
    """The recipe's own tags, all of them: any not given are taken off. Its
    source's come with it regardless."""
    recipe = await _recipe_or_404(session, recipe_id, user)
    await _editable_source(session, recipe.source_id, user)
    wanted = await _known(session, body.tags)
    await session.execute(delete(RecipeTag).where(RecipeTag.recipe_id == recipe.id))
    session.add_all(RecipeTag(recipe_id=recipe.id, tag_id=t) for t in wanted)
    await session.commit()
    return await recipe_tags(session, recipe)


@router.put("/api/sources/{source_id}/tags", response_model=list[TagOut], dependencies=[SameOrigin])
async def set_source_tags(
    source_id: uuid.UUID, body: TagsIn, user: CurrentUser, session: Session
) -> list[TagOut]:
    """The source's tags, all of them, which every recipe in it has too."""
    source: Source = await _editable_source(session, source_id, user)
    wanted = await _known(session, body.tags)
    await session.execute(delete(SourceTag).where(SourceTag.source_id == source.id))
    session.add_all(SourceTag(source_id=source.id, tag_id=t) for t in wanted)
    await session.commit()
    return await source_tags(session, source.id)
