"""The admin overview's numbers about the catalog, for moderators.

One so far (*Ray's equipment spec, 2026-11-15*: "the admin overview shows
how many recipes have equipment recorded, as a percentage"). A recipe's
equipment is recorded when it lists a need or says it needs nothing
special; one nobody has looked at is neither (needs.py).

It counts the recipes anyone can see: published, in a published source
that isn't a private collection. A recipe in someone's family collection
is counted nowhere, so the numbers are the same for every moderator and
say nothing of what a moderator can't see. Recipes waiting for review
aren't counted either: the share is of the catalog as it's published.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import exists, func, or_, select

from openlarder import visibility
from openlarder.auth import ModeratorUser
from openlarder.db import Session
from openlarder.models import Recipe, RecipeEquipment

router = APIRouter(prefix="/api/admin/overview", tags=["admin"])


def share(part: int, whole: int) -> str:
    """A part of a whole as a percentage to say in a sentence: "12%".

    Rounded to a whole number, except at the ends, where rounding would
    say something untrue: one recipe of ten thousand is "under 1%" and not
    "0%", and all but one is "over 99%" and not "100%". Nothing of nothing
    is no share at all, and the empty string.
    """
    if whole <= 0:
        return ""
    if part <= 0:
        return "0%"
    if part >= whole:
        return "100%"
    percent = 100 * part / whole
    if percent < 1:
        return "under 1%"
    if percent > 99:
        return "over 99%"
    # Halves go up, as people round them: round() would call 12.5 twelve.
    return f"{(200 * part + whole) // (2 * whole)}%"


class EquipmentRecorded(BaseModel):
    # Published recipes anyone can see, and those of them with equipment
    # recorded: a need listed, or nothing special said.
    recipes: int
    recorded: int
    # `recorded` of `recipes`, as share() says it; empty with no recipes.
    share: str


class Overview(BaseModel):
    equipment: EquipmentRecorded


@router.get("", response_model=Overview)
async def overview(moderator: ModeratorUser, session: Session) -> Overview:
    has_needs = exists().where(RecipeEquipment.recipe_id == Recipe.id)
    recipes, recorded = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(or_(Recipe.equipment_checked, has_needs)),
            )
            .select_from(Recipe)
            # What someone signed out sees, whoever is asking.
            .where(visibility.recipes_seen_by(None))
        )
    ).one()
    return Overview(
        equipment=EquipmentRecorded(
            recipes=recipes, recorded=recorded, share=share(recorded, recipes)
        )
    )
