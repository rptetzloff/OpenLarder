"""Tags on sources and recipes, as pages show them (routers/tags.py sets
them). A source's tags are its recipes' too."""

import uuid

from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.models import Recipe, RecipeTag, SourceTag, Tag, TagKind

# The kinds in the order pages show them.
KIND_ORDER = [TagKind.DIET, TagKind.COURSE, TagKind.CUISINE, TagKind.TECHNIQUE]
MAX_TAGS = 30


class TagOut(BaseModel):
    id: uuid.UUID
    kind: TagKind
    name: str


class RecipeTagOut(TagOut):
    # Set on the recipe's source rather than the recipe: it can only be
    # taken off there.
    from_source: bool = False


def order():
    rank = case(*((Tag.kind == k, n) for n, k in enumerate(KIND_ORDER)))
    return (rank, func.lower(Tag.name))


def tag_out(tag: Tag) -> TagOut:
    return TagOut(id=tag.id, kind=tag.kind, name=tag.name)


async def recipe_tags(session: AsyncSession, recipe: Recipe) -> list[RecipeTagOut]:
    """The recipe's tags: its own, and its source's, each once."""
    own = select(RecipeTag.tag_id).where(RecipeTag.recipe_id == recipe.id)
    inherited = select(SourceTag.tag_id).where(SourceTag.source_id == recipe.source_id)
    rows = await session.scalars(
        select(Tag).where(Tag.id.in_(own) | Tag.id.in_(inherited)).order_by(*order())
    )
    from_source = set(await session.scalars(inherited))
    mine = set(await session.scalars(own))
    return [
        RecipeTagOut(
            id=t.id, kind=t.kind, name=t.name, from_source=t.id in from_source and t.id not in mine
        )
        for t in rows
    ]


async def source_tags(session: AsyncSession, source_id: uuid.UUID) -> list[TagOut]:
    rows = await session.scalars(
        select(Tag)
        .join(SourceTag, SourceTag.tag_id == Tag.id)
        .where(SourceTag.source_id == source_id)
        .order_by(*order())
    )
    return [tag_out(t) for t in rows]
