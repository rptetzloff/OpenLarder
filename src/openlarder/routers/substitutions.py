"""Substitutions and the diets they serve: listing diets, and adding or
removing swaps (admins). Swaps are read on the ingredient and recipe pages;
see substitutions.py."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from openlarder import substitutions
from openlarder.auth import ModeratorUser, SameOrigin
from openlarder.db import Session
from openlarder.models import Substitution, Tag, TagKind

router = APIRouter(tags=["substitutions"])


class Diet(BaseModel):
    id: uuid.UUID
    name: str


class ThingOut(BaseModel):
    kind: Literal["ingredient", "recipe"]
    id: uuid.UUID
    name: str


class SourceOut(BaseModel):
    source_id: uuid.UUID
    source_title: str
    edition_id: uuid.UUID
    page: str | None


class SwapOut(BaseModel):
    id: uuid.UUID
    instead_of: ThingOut
    use: ThingOut
    diet: Diet | None
    # None: contributed rather than printed in a book.
    source: SourceOut | None
    note: str | None


def swap_out(s: substitutions.Listed) -> SwapOut:
    return SwapOut(
        id=s.id,
        instead_of=ThingOut(kind=s.instead_of.kind, id=s.instead_of.id, name=s.instead_of.name),
        use=ThingOut(kind=s.use.kind, id=s.use.id, name=s.use.name),
        diet=Diet(id=s.diet[0], name=s.diet[1]) if s.diet else None,
        source=SourceOut(
            source_id=s.source[0],
            source_title=s.source[1],
            edition_id=s.source[2],
            page=s.source[3],
        )
        if s.source
        else None,
        note=s.note,
    )


@router.get("/api/diets", response_model=list[Diet])
async def list_diets(session: Session) -> list[Diet]:
    rows = await session.execute(
        select(Tag.id, Tag.name).where(Tag.kind == TagKind.DIET).order_by(func.lower(Tag.name))
    )
    return [Diet(id=i, name=n) for i, n in rows]


class DietIn(BaseModel):
    name: str = Field(max_length=60)


@router.post("/api/diets", response_model=Diet, dependencies=[SameOrigin])
async def add_diet(body: DietIn, admin: ModeratorUser, session: Session) -> Diet:
    """A new diet, or the one already by that name."""
    try:
        diet = await substitutions.add_diet(session, body.name)
    except substitutions.InvalidSwap as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await session.commit()
    return Diet(id=diet.id, name=diet.name)


class SideIn(BaseModel):
    ingredient_id: uuid.UUID | None = None
    recipe_id: uuid.UUID | None = None


class SwapIn(BaseModel):
    instead_of: SideIn
    use: SideIn
    diet_id: uuid.UUID | None = None
    source_edition_id: uuid.UUID | None = None
    source_page: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=600)


@router.post(
    "/api/substitutions",
    response_model=SwapOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def add_swap(body: SwapIn, admin: ModeratorUser, session: Session) -> SwapOut:
    try:
        row = await substitutions.add(
            session,
            substitutions.SwapIn(
                instead_of=substitutions.Side(
                    body.instead_of.ingredient_id, body.instead_of.recipe_id
                ),
                use=substitutions.Side(body.use.ingredient_id, body.use.recipe_id),
                diet_id=body.diet_id,
                source_edition_id=body.source_edition_id,
                source_page=body.source_page,
                note=body.note,
            ),
        )
    except substitutions.InvalidSwap as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except substitutions.AlreadyThere as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    await session.commit()
    [listed] = await substitutions.listed(session, Substitution.id == row.id)
    return swap_out(listed)


@router.delete(
    "/api/substitutions/{swap_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SameOrigin],
)
async def remove_swap(swap_id: uuid.UUID, admin: ModeratorUser, session: Session) -> Response:
    swap = await session.get(Substitution, swap_id)
    if swap is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such swap.")
    await session.delete(swap)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
