"""Allergens on ingredients: what the catalog records, and what a narrower
ingredient inherits from a broader one (migration 0059).

*SCOPING.md, Allergen data (Ray, 2026-11-06):* presented as crowdsourced
information, wherever it appears, with a notice that it's unverified, is
about ingredients in general and not any product, and is no guarantee a
recipe is safe for anyone. The site never says a recipe is safe for an
allergy: a recipe lists only what its ingredients record as containing or
maybe containing, never that it's free of anything.

Meat, poultry and pork are recorded the same way, in the same list
(migration 0064; *Ray, 2026-11-11*): diets avoid them, and poultry is an
allergy too.

An ingredient records, for any allergen, that it contains it, may contain
it (oats, often processed alongside wheat), or doesn't. A narrower
ingredient inherits each from the nearest broader one recording it, so
Cheddar under Cheese contains milk when Cheese does, and "doesn't" is how
Vegan Butter under Butter says otherwise.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import bindparam, delete, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.models import Allergen, Ingredient, IngredientAllergen
from openlarder.models.allergens import STATUSES

NOTICE = (
    "Allergen and meat information here is crowdsourced and unverified. It describes ingredients in"
    " general, not any product: one brand's stock may contain milk when another's doesn't,"
    " and oats may be processed alongside wheat. It isn't a guarantee that a recipe is safe"
    " for anyone, so check the labels on what you buy."
)

# How far up the hierarchy to look; set_parent makes no loops, but rows
# written another way could.
DEPTH = 32


@dataclass(frozen=True)
class Record:
    allergen: str
    status: str
    # The ingredient it's recorded on: itself, or a broader one.
    on: uuid.UUID


async def listed(session: AsyncSession) -> list[Allergen]:
    return list(await session.scalars(select(Allergen).order_by(Allergen.position)))


_RECORDED = text(
    """
    WITH RECURSIVE up (root, id, depth) AS (
      SELECT id, id, 0 FROM ingredients WHERE id = ANY(:ids)
      UNION ALL
      SELECT up.root, i.parent_id, up.depth + 1
      FROM up JOIN ingredients i ON i.id = up.id
      WHERE i.parent_id IS NOT NULL AND up.depth < :depth
    )
    SELECT DISTINCT ON (up.root, a.allergen) up.root, a.allergen, a.status, a.ingredient_id
    FROM up JOIN ingredient_allergens a ON a.ingredient_id = up.id
    ORDER BY up.root, a.allergen, up.depth
    """
).bindparams(bindparam("ids", type_=ARRAY(UUID(as_uuid=True))))


async def recorded(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Record]]:
    """Each ingredient's allergens, its own or the nearest broader one's,
    by allergen; "doesn't contain" included."""
    out: dict[uuid.UUID, dict[str, Record]] = {i: {} for i in ids}
    if not ids:
        return out
    for root, allergen, status, on in await session.execute(
        _RECORDED, {"ids": list(ids), "depth": DEPTH}
    ):
        out[root][allergen] = Record(allergen, status, on)
    return out


class Unknown(ValueError):
    """An allergen or status the catalog doesn't have."""


async def record(session: AsyncSession, ingredient: Ingredient, statuses: dict[str, str]) -> None:
    """Set what this ingredient records, allergen by allergen; one left out
    records nothing, and inherits."""
    known = {a.key for a in await listed(session)}
    for key, status in statuses.items():
        if key not in known:
            raise Unknown(f"There's no allergen “{key}” here.")
        if status not in STATUSES:
            raise Unknown(f"“{status}” isn't contains, may_contain or free.")
    own = {
        a.allergen: a
        for a in await session.scalars(
            select(IngredientAllergen).where(IngredientAllergen.ingredient_id == ingredient.id)
        )
    }
    gone = [key for key in own if key not in statuses]
    if gone:
        await session.execute(
            delete(IngredientAllergen).where(
                IngredientAllergen.ingredient_id == ingredient.id,
                IngredientAllergen.allergen.in_(gone),
            )
        )
    for key, status in statuses.items():
        if key in own:
            own[key].status = status
        else:
            session.add(
                IngredientAllergen(ingredient_id=ingredient.id, allergen=key, status=status)
            )
    await session.flush()


async def merge(session: AsyncSession, source: uuid.UUID, target: uuid.UUID) -> None:
    """An ingredient merged into another: what it records moves across,
    where the other records nothing for that allergen."""
    taken = select(IngredientAllergen.allergen).where(IngredientAllergen.ingredient_id == target)
    await session.execute(
        delete(IngredientAllergen).where(
            IngredientAllergen.ingredient_id == source, IngredientAllergen.allergen.in_(taken)
        )
    )
    await session.execute(
        update(IngredientAllergen)
        .where(IngredientAllergen.ingredient_id == source)
        .values(ingredient_id=target)
    )
