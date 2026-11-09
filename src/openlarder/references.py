"""Storing each line's options, and the recipes its page references mean.

lines.py works out a line's options and what a reference resolves to; this
writes that for a whole book at once. A book is the unit because a
reference can point at any recipe in it, including one added after the
recipe that cites it: adding, changing or removing a recipe, or importing a
batch, relinks the recipe's whole book. Relinking ends by matching the
book's options to canonical ingredients (ingredients.py).

Relinking is idempotent. An option already right is left as it is, so a
canonical ingredient matched to it later survives. Reference flags are
added once: one already raised, open or dealt with, isn't raised again, and
an open one that no longer applies is removed.
"""

import uuid
from collections import defaultdict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import ingredients, lines
from openlarder.models import (
    FlagKind,
    IngredientOption,
    Recipe,
    RecipeFlag,
    RecipeIngredient,
    RecipeLocation,
)

REFERENCE_KINDS = (FlagKind.REFERENCE_PAGE.value, FlagKind.UNKNOWN_REFERENCE.value)


async def book_recipes(
    session: AsyncSession, source_id: uuid.UUID
) -> tuple[list[lines.BookRecipe], dict[str, list[lines.BookRecipe]]]:
    """The source's recipes with their pages, and keyed by title, for
    lines.resolve."""
    titles = {
        recipe_id: title
        for recipe_id, title in await session.execute(
            select(Recipe.id, Recipe.title).where(Recipe.source_id == source_id)
        )
    }
    pages: dict[uuid.UUID, set[str]] = defaultdict(set)
    for recipe_id, page in await session.execute(
        select(RecipeLocation.recipe_id, RecipeLocation.page).where(
            RecipeLocation.source_id == source_id, RecipeLocation.page.is_not(None)
        )
    ):
        pages[recipe_id].add(page)
    book = [lines.BookRecipe(r, t, frozenset(pages[r])) for r, t in titles.items()]
    by_title: dict[str, list[lines.BookRecipe]] = defaultdict(list)
    for recipe in book:
        by_title[recipe.title.casefold()].append(recipe)
    return book, by_title


async def relink(session: AsyncSession, source_id: uuid.UUID) -> None:
    book, by_title = await book_recipes(session, source_id)

    existing: dict[uuid.UUID, list[IngredientOption]] = defaultdict(list)
    for option in await session.scalars(
        select(IngredientOption)
        .join(Recipe, Recipe.id == IngredientOption.recipe_id)
        .where(Recipe.source_id == source_id)
        .order_by(IngredientOption.rank)
    ):
        existing[option.recipe_ingredient_id].append(option)

    wanted_flags: set[tuple[uuid.UUID, str, str]] = set()
    for line in await session.scalars(
        select(RecipeIngredient)
        .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
        .where(Recipe.source_id == source_id)
    ):
        wanted = []
        for option in lines.options(line.original_text):
            resolved = lines.resolve(line.recipe_id, option, book, by_title)
            wanted.append((option.name, resolved.recipe_id))
            if resolved.flag:
                wanted_flags.add((line.recipe_id, resolved.flag[0].value, resolved.flag[1]))
        have = existing.get(line.id, [])
        if [(o.name, o.sub_recipe_id) for o in have] == wanted:
            continue
        for option in have:
            await session.delete(option)
        await session.flush()
        for rank, (name, sub_recipe_id) in enumerate(wanted, start=1):
            session.add(
                IngredientOption(
                    recipe_ingredient_id=line.id,
                    recipe_id=line.recipe_id,
                    rank=rank,
                    name=name,
                    sub_recipe_id=sub_recipe_id,
                )
            )
    await session.flush()

    raised = (
        await session.execute(
            select(RecipeFlag)
            .join(Recipe, Recipe.id == RecipeFlag.recipe_id)
            .where(Recipe.source_id == source_id, RecipeFlag.kind.in_(REFERENCE_KINDS))
        )
    ).scalars()
    seen = set()
    for flag in raised:
        key = (flag.recipe_id, flag.kind, flag.detail)
        seen.add(key)
        if key not in wanted_flags and flag.resolved_at is None:
            await session.delete(flag)
    for recipe_id, kind, detail in wanted_flags - seen:
        session.add(RecipeFlag(recipe_id=recipe_id, kind=kind, detail=detail))
    await session.flush()
    # Options just written, and any never matched, get their ingredients.
    await ingredients.match_book(session, source_id)


async def release(session: AsyncSession, recipe_id: uuid.UUID) -> None:
    """Unlink every reference to a recipe about to be removed.

    The options' foreign key restricts deleting a recipe still used as a
    component; relinking the book afterwards finds what they mean now.
    """
    await session.execute(
        update(IngredientOption)
        .where(IngredientOption.sub_recipe_id == recipe_id)
        .values(sub_recipe_id=None)
    )
