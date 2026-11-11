"""Substitutions and the diets they serve: listing diets, and adding or
removing swaps (admins). Swaps are read on the ingredient and recipe pages;
see substitutions.py."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from openlarder import allergens, diets, substitutions, visibility
from openlarder.auth import ModeratorUser, SameOrigin, Viewer
from openlarder.db import Session
from openlarder.models import Recipe, Substitution, Tag, TagKind

router = APIRouter(tags=["substitutions"])


class Diet(BaseModel):
    id: uuid.UUID
    name: str
    # The allergens it avoids (diets.py), for a recipe's page to check.
    avoids: list[str] = []


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
    avoids = await diets.avoided(session)
    order = {a.key: a.position for a in await allergens.listed(session)}
    return [
        Diet(id=i, name=n, avoids=sorted(avoids.get(i, ()), key=lambda k: order.get(k, 99)))
        for i, n in rows
    ]


class AvoidsIn(BaseModel):
    allergens: list[str] = Field(max_length=50)


@router.put("/api/diets/{diet_id}/allergens", response_model=Diet, dependencies=[SameOrigin])
async def set_diet_allergens(
    diet_id: uuid.UUID, body: AvoidsIn, moderator: ModeratorUser, session: Session
) -> Diet:
    """Which allergens a diet avoids; answers with the diet."""
    diet = await session.get(Tag, diet_id)
    if diet is None or diet.kind != TagKind.DIET:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such diet.")
    known = {a.key for a in await allergens.listed(session)}
    unknown = sorted(set(body.allergens) - known)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"There's no allergen “{unknown[0]}” here."
        )
    await diets.set_avoided(session, diet.id, set(body.allergens))
    await session.commit()
    return next(d for d in await list_diets(session) if d.id == diet.id)


class Found(BaseModel):
    key: str
    label: str
    status: Literal["contains", "may_contain"]


class DietLine(BaseModel):
    ingredient: ThingOut
    # The allergens it records that the diet avoids.
    found: list[Found]
    # Swaps recorded for it, or for a broader ingredient, for a diet that
    # avoids those too.
    swaps: list[SwapOut]


class DietCheck(BaseModel):
    diet: Diet
    lines: list[DietLine]
    notice: str


@router.get("/api/recipes/{recipe_id}/diets/{diet_id}", response_model=DietCheck)
async def check_recipe(
    recipe_id: uuid.UUID, diet_id: uuid.UUID, session: Session, viewer: Viewer
) -> DietCheck:
    """The recipe's ingredients that record an allergen the diet avoids,
    with the swaps recorded for them (diets.py). Never says that the
    recipe suits the diet."""
    seen = await session.scalar(
        select(Recipe.id).where(Recipe.id == recipe_id, visibility.recipes_seen_by(viewer))
    )
    if seen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe.")
    diet = next((d for d in await list_diets(session) if d.id == diet_id), None)
    if diet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such diet.")
    labels = {a.key: a.label for a in await allergens.listed(session)}
    lines = await diets.check(session, recipe_id, diet_id, viewer)
    return DietCheck(
        diet=diet,
        lines=[
            DietLine(
                ingredient=ThingOut(kind="ingredient", id=line.ingredient_id, name=line.name),
                found=[
                    Found(key=k, label=labels.get(k, k), status=line.found[k])
                    for k in diet.avoids
                    if k in line.found
                ],
                swaps=[swap_out(x) for x in line.swaps],
            )
            for line in lines
        ],
        notice=allergens.NOTICE,
    )


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
