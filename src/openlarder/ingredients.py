"""Canonical ingredients: matching each line's options to one.

The canonical list starts from the catalog's own names, which follow the
entry rules already ("Yellow Onion", "Fresh Ginger"), not from FoodData
Central's ("Onions, raw"). *Ray, 2026-11-07.* An option is matched by its
key, which ignores case, plurals and punctuation, so "Cinnamon Sticks" and
"cinnamon stick" are one ingredient. An option no ingredient has the key
of becomes a new ingredient, named as it was written: until review exists,
admins' entries publish at once, and merging is how a wrong one is fixed.

Options that cite a page ("Filling (p. 205)") are components, not
ingredients, whether or not references.py could link them, and are left
unmatched; every option linked to a recipe is one of them.
"""

import re
import uuid
from collections import Counter, defaultdict

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import lines
from openlarder.models import Ingredient, IngredientOption, Recipe, RecipeIngredient


def _stem(word: str) -> str:
    """Enough of a word that singular and plural meet: "berries" and "berry"
    are both "berri", "tomatoes" and "tomato" both "tomato"."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    if len(word) > 3 and word.endswith("y"):
        word = word[:-1] + "i"
    return word


def match_key(name: str) -> str:
    """The key an ingredient is matched by. Accents are kept: "Rosé" is not
    "Rose"."""
    words = re.findall(r"[^\W_]+", name.casefold().replace("&", " and "))
    return " ".join(_stem(w) for w in words)


async def match_book(session: AsyncSession, work_id: uuid.UUID) -> None:
    """Match every unmatched option in the book to a canonical ingredient."""
    rows = (
        await session.execute(
            select(IngredientOption.id, IngredientOption.rank, RecipeIngredient.original_text)
            .join(RecipeIngredient, RecipeIngredient.id == IngredientOption.recipe_ingredient_id)
            .join(Recipe, Recipe.id == IngredientOption.recipe_id)
            .where(
                Recipe.work_id == work_id,
                IngredientOption.ingredient_id.is_(None),
            )
        )
    ).all()
    wanted: dict[uuid.UUID, str] = {}
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    for option_id, rank, text in rows:
        read = lines.options(text)
        if rank > len(read) or read[rank - 1].page is not None:
            continue
        name = read[rank - 1].name
        if key := match_key(name):
            wanted[option_id] = key
            spellings[key][name] += 1
    if not wanted:
        return

    known = await _ids(session, set(spellings))
    new = [
        # The spelling the book uses most; the first written on a tie.
        {"name": counts.most_common(1)[0][0], "match_key": key}
        for key, counts in spellings.items()
        if key not in known
    ]
    if new:
        # Another request may add the same ingredient meanwhile; its row is
        # as good as this one.
        await session.execute(insert(Ingredient).values(new).on_conflict_do_nothing())
        known |= await _ids(session, {n["match_key"] for n in new})
    matches = [
        {"id": option_id, "ingredient_id": known[key]}
        for option_id, key in wanted.items()
        if key in known
    ]
    if matches:
        await session.execute(update(IngredientOption), matches)


async def _ids(session: AsyncSession, keys: set[str]) -> dict[str, uuid.UUID]:
    found: dict[str, uuid.UUID] = {}
    for chunk in _chunks(sorted(keys), 1000):
        for key, ingredient_id in await session.execute(
            select(Ingredient.match_key, Ingredient.id).where(Ingredient.match_key.in_(chunk))
        ):
            found[key] = ingredient_id
    return found


def _chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
