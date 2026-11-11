"""Allergens: the list, with the notice shown wherever they are, and what an
ingredient records (allergens.py). Reading is public; moderators record."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from openlarder import allergens, visibility
from openlarder.auth import ModeratorUser, SameOrigin
from openlarder.db import Session
from openlarder.models import Ingredient

router = APIRouter(tags=["allergens"])

Status = Literal["contains", "may_contain", "free"]


class AllergenOut(BaseModel):
    key: str
    label: str


class AllergenList(BaseModel):
    allergens: list[AllergenOut]
    # Shown wherever allergen information is (SCOPING.md, Allergen data).
    notice: str


class Broader(BaseModel):
    id: uuid.UUID
    name: str


class IngredientAllergenOut(BaseModel):
    key: str
    label: str
    status: Status
    # Recorded on a broader ingredient: which, if the viewer may see it.
    inherited: bool = False
    inherited_from: Broader | None = None


class InRecipe(BaseModel):
    id: uuid.UUID
    name: str
    status: Literal["contains", "may_contain"]


class RecipeAllergenOut(BaseModel):
    key: str
    label: str
    # contains, if any of its ingredients does; else may_contain.
    status: Literal["contains", "may_contain"]
    ingredients: list[InRecipe]


@router.get("/api/allergens", response_model=AllergenList)
async def allergen_list(session: Session) -> AllergenList:
    return AllergenList(
        allergens=[AllergenOut(key=a.key, label=a.label) for a in await allergens.listed(session)],
        notice=allergens.NOTICE,
    )


async def for_ingredient(session, ingredient_id: uuid.UUID, viewer) -> list[IngredientAllergenOut]:
    """What an ingredient records, or inherits, in the list's order."""
    found = (await allergens.recorded(session, [ingredient_id]))[ingredient_id]
    broader = {r.on for r in found.values() if r.on != ingredient_id}
    names = {}
    if broader:
        names = dict(
            (
                await session.execute(
                    select(Ingredient.id, Ingredient.name).where(
                        Ingredient.id.in_(broader), visibility.ingredients_seen_by(viewer)
                    )
                )
            ).all()
        )
    out = []
    for a in await allergens.listed(session):
        if (r := found.get(a.key)) is None:
            continue
        inherited = r.on != ingredient_id
        out.append(
            IngredientAllergenOut(
                key=a.key,
                label=a.label,
                status=r.status,
                inherited=inherited,
                inherited_from=(
                    Broader(id=r.on, name=names[r.on]) if inherited and r.on in names else None
                ),
            )
        )
    return out


async def for_recipe(session, used: dict[uuid.UUID, str]) -> list[RecipeAllergenOut]:
    """What a recipe's ingredients (id: name) record as containing or maybe
    containing; never what they don't."""
    found = await allergens.recorded(session, list(used))
    out = []
    for a in await allergens.listed(session):
        those = [
            InRecipe(id=i, name=name, status=found[i][a.key].status)
            for i, name in used.items()
            if a.key in found[i] and found[i][a.key].status != "free"
        ]
        if those:
            out.append(
                RecipeAllergenOut(
                    key=a.key,
                    label=a.label,
                    status=(
                        "contains" if any(x.status == "contains" for x in those) else "may_contain"
                    ),
                    ingredients=those,
                )
            )
    return out


class AllergensIn(BaseModel):
    # Allergen: status; one left out records nothing, and is inherited.
    statuses: dict[str, Status]


@router.put(
    "/api/ingredients/{ingredient_id}/allergens",
    response_model=list[IngredientAllergenOut],
    dependencies=[SameOrigin],
)
async def set_allergens(
    ingredient_id: uuid.UUID, body: AllergensIn, moderator: ModeratorUser, session: Session
) -> list[IngredientAllergenOut]:
    """Record what this ingredient contains, may contain or doesn't;
    answers with what it records and inherits."""
    ingredient = await session.scalar(
        select(Ingredient).where(
            Ingredient.id == ingredient_id, visibility.ingredients_seen_by(moderator)
        )
    )
    if ingredient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such ingredient.")
    try:
        await allergens.record(session, ingredient, body.statuses)
    except allergens.Unknown as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    await session.commit()
    return await for_ingredient(session, ingredient_id, moderator)
