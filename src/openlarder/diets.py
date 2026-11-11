"""Cooking a recipe for a diet: which of its ingredients record an allergen
the diet avoids, and the swaps recorded for them (migration 0061).

*SCOPING.md, Allergen data: "This lets the site offer substitutions for a
diet automatically, not only where someone has entered one."* A swap is
offered for a line when it's recorded for that ingredient or a broader
one (a swap for Butter serves Unsalted Butter), for a diet that avoids
everything the line was found for (a Vegan swap for butter serves
Dairy-Free too), and what it puts in doesn't record one of those itself.

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
    """Each diet's allergens, for the diets that avoid any."""
    out: dict[uuid.UUID, set[str]] = defaultdict(set)
    for diet, key in await session.execute(select(DietAllergen.diet_tag_id, DietAllergen.allergen)):
        out[diet].add(key)
    return dict(out)


async def set_avoided(session: AsyncSession, diet_id: uuid.UUID, keys: set[str]) -> None:
    have = set(
        await session.scalars(
            select(DietAllergen.allergen).where(DietAllergen.diet_tag_id == diet_id)
        )
    )
    for key in have - keys:
        row = await session.get(DietAllergen, (diet_id, key))
        await session.delete(row)
    for key in keys - have:
        session.add(DietAllergen(diet_tag_id=diet_id, allergen=key))
    await session.flush()


@dataclass
class Line:
    ingredient_id: uuid.UUID
    name: str
    # Allergen: contains or may_contain, those the diet avoids.
    found: dict[str, str]
    swaps: list[substitutions.Listed] = field(default_factory=list)


async def check(
    session: AsyncSession, recipe_id: uuid.UUID, diet_id: uuid.UUID, viewer
) -> list[Line]:
    """The recipe's ingredients that record an allergen the diet avoids, in
    the order of its lines, each with the swaps that serve it."""
    diets = await avoided(session)
    avoid = diets.get(diet_id, set())
    if not avoid:
        return []
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
    recorded = await allergens.recorded(session, list(names))
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
