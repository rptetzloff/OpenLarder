"""Substitutions and the diets they serve: listing diets, adding, renaming
and removing them, and adding or removing swaps (moderators). Swaps are read
on the ingredient and recipe pages; see substitutions.py."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import allergens, diets, substitutions, visibility
from openlarder.auth import ModeratorUser, SameOrigin, Viewer
from openlarder.db import Session
from openlarder.models import (
    Ingredient,
    Recipe,
    RecipeTag,
    Source,
    SourceTag,
    Substitution,
    Tag,
    TagKind,
)

router = APIRouter(tags=["substitutions"])


class Pair(BaseModel):
    allergen: str
    other: str


class Diet(BaseModel):
    id: uuid.UUID
    name: str
    # The allergens it avoids (diets.py), for a recipe's page to check.
    avoids: list[str] = []
    # Those it avoids only together: Kosher's meat with milk.
    together: list[Pair] = []


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
    together = await diets.avoided_together(session)
    order = {a.key: a.position for a in await allergens.listed(session)}
    return [
        Diet(
            id=i,
            name=n,
            avoids=sorted(avoids.get(i, ()), key=lambda k: order.get(k, 99)),
            together=[
                Pair(allergen=a, other=b)
                for a, b in sorted(together.get(i, ()), key=lambda p: order.get(p[0], 99))
            ],
        )
        for i, n in rows
    ]


class AvoidsIn(BaseModel):
    allergens: list[str] = Field(max_length=50)


@router.put("/api/diets/{diet_id}/allergens", response_model=Diet, dependencies=[SameOrigin])
async def set_diet_allergens(
    diet_id: uuid.UUID, body: AvoidsIn, moderator: ModeratorUser, session: Session
) -> Diet:
    """Which allergens a diet avoids; answers with the diet."""
    diet = await _diet_or_404(session, diet_id)
    await diets.set_avoided(session, diet.id, await _known(session, body.allergens))
    await session.commit()
    return await _listed(session, diet.id)


async def _diet_or_404(session: AsyncSession, diet_id: uuid.UUID) -> Tag:
    diet = await session.get(Tag, diet_id)
    if diet is None or diet.kind != TagKind.DIET:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such diet.")
    return diet


async def _known(session: AsyncSession, keys: list[str]) -> set[str]:
    known = {a.key for a in await allergens.listed(session)}
    unknown = sorted(set(keys) - known)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"There's no allergen “{unknown[0]}” here."
        )
    return set(keys)


async def _listed(session: AsyncSession, diet_id: uuid.UUID) -> Diet:
    """The diet as the list has it, with what it avoids."""
    return next(d for d in await list_diets(session) if d.id == diet_id)


async def _named(session: AsyncSession, name: str, but: uuid.UUID | None = None) -> Tag | None:
    """The diet already called this, whatever its capitals, other than one."""
    return await session.scalar(
        select(Tag).where(
            Tag.kind == TagKind.DIET,
            func.lower(Tag.name) == name.lower(),
            *([Tag.id != but] if but else []),
        )
    )


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


class Has(BaseModel):
    ingredient: ThingOut
    status: Literal["contains", "may_contain"]


class TogetherOut(BaseModel):
    """Two things the diet avoids together, both recorded in this recipe."""

    allergen: Found
    other: Found
    has: list[Has]
    has_other: list[Has]


class DietCheck(BaseModel):
    diet: Diet
    lines: list[DietLine]
    together: list[TogetherOut] = []
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

    def side(key: str, has: list) -> tuple[Found, list[Has]]:
        # "Contains" when any ingredient does.
        status = "contains" if any(s == "contains" for _, _, s in has) else "may_contain"
        return Found(key=key, label=labels.get(key, key), status=status), [
            Has(ingredient=ThingOut(kind="ingredient", id=i, name=n), status=s) for i, n, s in has
        ]

    together = []
    for t in await diets.check_together(session, recipe_id, diet_id):
        a, has = side(t.allergen, t.has)
        b, has_other = side(t.other, t.has_other)
        together.append(TogetherOut(allergen=a, other=b, has=has, has_other=has_other))
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
        together=together,
        notice=allergens.NOTICE,
    )


class DietIn(BaseModel):
    name: str = Field(max_length=60)
    # Admin's form says what the new diet avoids, and is told when the name
    # is taken. A swap's form gives only a name, and gets the diet by it.
    allergens: list[str] | None = Field(default=None, max_length=50)


@router.post("/api/diets", response_model=Diet, dependencies=[SameOrigin])
async def add_diet(body: DietIn, admin: ModeratorUser, session: Session) -> Diet:
    """A new diet, or the one already by that name. With what it avoids, a
    new one only: a name already a diet's is refused, so that one's list
    isn't written over by mistake."""
    if body.allergens is not None:
        avoids = await _known(session, body.allergens)
        taken = await _named(session, " ".join(body.name.split()))
        if taken is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"“{taken.name}” is a diet already.")
    try:
        diet = await substitutions.add_diet(session, body.name)
    except substitutions.InvalidSwap as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    if body.allergens is not None:
        await diets.set_avoided(session, diet.id, avoids)
    await session.commit()
    return await _listed(session, diet.id)


class DietName(BaseModel):
    name: str = Field(max_length=60)


@router.patch("/api/diets/{diet_id}", response_model=Diet, dependencies=[SameOrigin])
async def rename_diet(
    diet_id: uuid.UUID, body: DietName, moderator: ModeratorUser, session: Session
) -> Diet:
    """A diet's name, everywhere it's shown: it stays on the recipes and
    sources tagged with it, and the swaps recorded for it. *Ray, 2026-11-14.*"""
    diet = await _diet_or_404(session, diet_id)
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the diet a name.")
    taken = await _named(session, name, but=diet.id)
    if taken is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"“{taken.name}” is a diet already.")
    diet.name = name
    await session.commit()
    return await _listed(session, diet.id)


class DietUse(BaseModel):
    """What removing a diet would take with it, for the question asked
    first. The catalog's recipes and sources only: a family's own aren't
    counted, so the number says nothing about what a family has tagged."""

    recipes: int
    sources: int
    # Swaps hold a diet where it is. The ingredients they're recorded for,
    # to find them by; one for a recipe is on that recipe's page.
    swaps: int
    swap_ingredients: list[ThingOut]


async def _swaps(session: AsyncSession, diet_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Substitution)
            .where(Substitution.diet_tag_id == diet_id)
        )
        or 0
    )


@router.get("/api/diets/{diet_id}/use", response_model=DietUse)
async def diet_use(diet_id: uuid.UUID, moderator: ModeratorUser, session: Session) -> DietUse:
    diet = await _diet_or_404(session, diet_id)
    public = select(Source.id).where(Source.private.is_(False))
    recipes = await session.scalar(
        select(func.count())
        .select_from(RecipeTag)
        .join(Recipe, Recipe.id == RecipeTag.recipe_id)
        .where(RecipeTag.tag_id == diet.id, Recipe.source_id.in_(public))
    )
    sources = await session.scalar(
        select(func.count())
        .select_from(SourceTag)
        .where(SourceTag.tag_id == diet.id, SourceTag.source_id.in_(public))
    )
    named = await session.execute(
        select(Ingredient.id, Ingredient.name)
        .where(
            Ingredient.id.in_(
                select(Substitution.from_ingredient_id).where(
                    Substitution.diet_tag_id == diet.id,
                    Substitution.from_ingredient_id.is_not(None),
                )
            ),
            visibility.ingredients_seen_by(moderator),
        )
        .order_by(func.lower(Ingredient.name))
    )
    return DietUse(
        recipes=recipes or 0,
        sources=sources or 0,
        swaps=await _swaps(session, diet.id),
        swap_ingredients=[ThingOut(kind="ingredient", id=i, name=n) for i, n in named],
    )


@router.delete(
    "/api/diets/{diet_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SameOrigin]
)
async def remove_diet(diet_id: uuid.UUID, moderator: ModeratorUser, session: Session) -> Response:
    """Takes a diet off the list, and off every recipe and source tagged
    with it, with what it avoids. One save, so Recent changes can undo it
    whole. Refused while a swap is recorded for it: a swap is something a
    book says, and is removed on its own page first. *Ray, 2026-11-14.*"""
    diet = await _diet_or_404(session, diet_id)
    swaps = await _swaps(session, diet.id)
    if swaps:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{swaps} {'swap is' if swaps == 1 else 'swaps are'} recorded for {diet.name}."
            " Remove those first.",
        )
    await session.delete(diet)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
