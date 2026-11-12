"""Cooking a recipe for a diet: which of its ingredients record an allergen
the diet avoids, and the swaps recorded for them (migration 0061).

*SCOPING.md, Allergen data: "This lets the site offer substitutions for a
diet automatically, not only where someone has entered one."* A swap is
offered for a line when it's recorded for that ingredient or a broader
one (a swap for Butter serves Unsalted Butter), for a diet that avoids
everything the line was found for (a Vegan swap for butter serves
Dairy-Free too), and what it puts in doesn't record one of those itself.

A diet may also avoid two things only together (migration 0066; *Ray,
2026-11-11*): Kosher keeps meat, and poultry, from milk. Those are found
across the whole recipe, not line by line, and no swap is offered for them.

Like everything about allergens, it says only what the catalog records,
never that a recipe suits a diet.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import allergens, ingredients, substitutions, visibility
from openlarder.models import (
    DietAllergen,
    Ingredient,
    IngredientOption,
    Recipe,
    RecipeIngredient,
    Source,
    Substitution,
)


async def avoided(session: AsyncSession) -> dict[uuid.UUID, set[str]]:
    """Each diet's allergens avoided outright, for the diets that avoid any."""
    out: dict[uuid.UUID, set[str]] = defaultdict(set)
    for diet, key in await session.execute(
        select(DietAllergen.diet_tag_id, DietAllergen.allergen).where(
            DietAllergen.with_allergen.is_(None)
        )
    ):
        out[diet].add(key)
    return dict(out)


async def avoided_together(session: AsyncSession) -> dict[uuid.UUID, list[tuple[str, str]]]:
    """Each diet's pairs: an allergen, and the one it's avoided with."""
    out: dict[uuid.UUID, list[tuple[str, str]]] = defaultdict(list)
    for diet, key, other in await session.execute(
        select(DietAllergen.diet_tag_id, DietAllergen.allergen, DietAllergen.with_allergen)
        .where(DietAllergen.with_allergen.is_not(None))
        .order_by(DietAllergen.allergen)
    ):
        out[diet].append((key, other))
    return dict(out)


async def set_avoided(session: AsyncSession, diet_id: uuid.UUID, keys: set[str]) -> None:
    """What a diet avoids outright; what it avoids only with another stays,
    unless it's now avoided outright."""
    rows = {
        row.allergen: row
        for row in await session.scalars(
            select(DietAllergen).where(DietAllergen.diet_tag_id == diet_id)
        )
    }
    for key, row in rows.items():
        if row.with_allergen is None and key not in keys:
            await session.delete(row)
        elif row.with_allergen is not None and key in keys:
            row.with_allergen = None
    for key in keys - set(rows):
        session.add(DietAllergen(diet_tag_id=diet_id, allergen=key))
    await session.flush()


@dataclass
class Line:
    ingredient_id: uuid.UUID
    name: str
    # Allergen: contains or may_contain, those the diet avoids.
    found: dict[str, str]
    swaps: list[substitutions.Listed] = field(default_factory=list)


@dataclass
class Together:
    allergen: str
    other: str
    # Each side's ingredients, in the recipe's order: id, name, status.
    has: list[tuple[uuid.UUID, str, str]]
    has_other: list[tuple[uuid.UUID, str, str]]


async def _recorded_in(session: AsyncSession, recipe_id: uuid.UUID):
    """The recipe's ingredients by id, in the order of its lines, and what
    each records."""
    used = (
        await session.execute(
            select(Ingredient.id, Ingredient.name)
            .join(IngredientOption, IngredientOption.ingredient_id == Ingredient.id)
            .join(RecipeIngredient, RecipeIngredient.id == IngredientOption.recipe_ingredient_id)
            .where(IngredientOption.recipe_id == recipe_id)
            .order_by(RecipeIngredient.position, IngredientOption.rank)
        )
    ).all()
    names = dict(used)
    return names, await allergens.recorded(session, list(names))


async def check_together(
    session: AsyncSession, recipe_id: uuid.UUID, diet_id: uuid.UUID
) -> list[Together]:
    """The pairs the diet avoids together that this recipe records both
    of, each with the ingredients recording either."""
    pairs = (await avoided_together(session)).get(diet_id, [])
    if not pairs:
        return []
    names, recorded = await _recorded_in(session, recipe_id)

    def having(key: str) -> list[tuple[uuid.UUID, str, str]]:
        return [
            (i, names[i], recorded[i][key].status)
            for i in names
            if key in recorded[i] and recorded[i][key].status != "free"
        ]

    found = []
    for key, other in pairs:
        has, has_other = having(key), having(other)
        if has and has_other:
            found.append(Together(key, other, has, has_other))
    return found


async def check(
    session: AsyncSession, recipe_id: uuid.UUID, diet_id: uuid.UUID, viewer
) -> list[Line]:
    """The recipe's ingredients that record an allergen the diet avoids, in
    the order of its lines, each with the swaps that serve it."""
    diets = await avoided(session)
    avoid = diets.get(diet_id, set())
    if not avoid:
        return []
    names, recorded = await _recorded_in(session, recipe_id)
    lines: list[Line] = []
    for i in names:
        found = {k: r.status for k, r in recorded[i].items() if k in avoid and r.status != "free"}
        if found:
            lines.append(Line(i, names[i], found))
    if not lines:
        return lines

    # Each ingredient and those above it.
    tree = ingredients.rooted_ancestry(*(line.ingredient_id for line in lines))
    above: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for root, i in await session.execute(select(tree.c.root, tree.c.id)):
        above[root].add(i)
    everyone_above = set().union(*above.values())
    swaps = await substitutions.listed(
        session,
        Substitution.from_ingredient_id.in_(everyone_above),
        Substitution.diet_tag_id.in_(list(diets)),
    )
    # Only what the viewer may see: the stand-in, and the book it's printed in.
    seen_ingredients = set(
        await session.scalars(
            select(Ingredient.id).where(
                Ingredient.id.in_(
                    [s.use.id for s in swaps if s.use.kind == "ingredient"] or [uuid.uuid4()]
                ),
                visibility.ingredients_seen_by(viewer),
            )
        )
    )
    seen_recipes = set(
        await session.scalars(
            select(Recipe.id).where(
                Recipe.id.in_(
                    [s.use.id for s in swaps if s.use.kind == "recipe"] or [uuid.uuid4()]
                ),
                visibility.recipes_seen_by(viewer),
            )
        )
    )
    seen_sources = set(
        await session.scalars(
            select(Source.id).where(
                Source.id.in_([s.source[0] for s in swaps if s.source] or [uuid.uuid4()]),
                visibility.sources_seen_by(viewer),
            )
        )
    )
    stand_ins = await allergens.recorded(
        session, [s.use.id for s in swaps if s.use.kind == "ingredient"]
    )
    for line in lines:
        for s in swaps:
            if s.instead_of.id not in above[line.ingredient_id]:
                continue
            # For a diet avoiding all this line was found for.
            if s.diet is None or not set(line.found) <= diets.get(s.diet[0], set()):
                continue
            if s.use.id not in (seen_ingredients if s.use.kind == "ingredient" else seen_recipes):
                continue
            if s.source and s.source[0] not in seen_sources:
                continue
            # What it puts in records one of them itself.
            own = stand_ins.get(s.use.id, {})
            if any(k in own and own[k].status != "free" for k in line.found):
                continue
            line.swaps.append(s)
    return lines
