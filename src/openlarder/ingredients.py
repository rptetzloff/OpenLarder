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

from sqlalchemy import ColumnElement, and_, delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from openlarder import lines
from openlarder.models import (
    Ingredient,
    IngredientAlias,
    IngredientOption,
    LarderItem,
    Recipe,
    RecipeIngredient,
    Substitution,
)


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


async def match_book(session: AsyncSession, source_id: uuid.UUID) -> None:
    """Match every unmatched option in the book to a canonical ingredient."""
    rows = (
        await session.execute(
            select(IngredientOption.id, IngredientOption.rank, RecipeIngredient.original_text)
            .join(RecipeIngredient, RecipeIngredient.id == IngredientOption.recipe_ingredient_id)
            .join(Recipe, Recipe.id == IngredientOption.recipe_id)
            .where(
                Recipe.source_id == source_id,
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


async def known_ids(session: AsyncSession, keys: set[str]) -> dict[str, uuid.UUID]:
    """The ingredient each key is the name or an alias of."""
    return await _ids(session, keys)


async def _ids(session: AsyncSession, keys: set[str]) -> dict[str, uuid.UUID]:
    """The ingredient each key is the name or an alias of."""
    found: dict[str, uuid.UUID] = {}
    for chunk in _chunks(sorted(keys), 1000):
        for query in (
            select(Ingredient.match_key, Ingredient.id),
            # A regional alias names something only where it's used.
            select(IngredientAlias.match_key, IngredientAlias.ingredient_id).where(
                IngredientAlias.region.is_(None)
            ),
        ):
            column = query.selected_columns[0]
            for key, i in await session.execute(query.where(column.in_(chunk))):
                found[key] = i
    return found


async def known(
    session: AsyncSession, keys: set[str], seen: ColumnElement[bool]
) -> dict[str, tuple[uuid.UUID, str, bool]]:
    """What _ids finds, among the ingredients seen, with each one's name and
    whether the key is another name for it, for the form to say what a line
    will be matched to."""
    found: dict[str, tuple[uuid.UUID, str, bool]] = {}
    for chunk in _chunks(sorted(keys), 1000):
        for query, alias in (
            (select(Ingredient.match_key, Ingredient.id, Ingredient.name), False),
            (
                select(IngredientAlias.match_key, Ingredient.id, Ingredient.name)
                .join(Ingredient, Ingredient.id == IngredientAlias.ingredient_id)
                .where(IngredientAlias.region.is_(None)),
                True,
            ),
        ):
            column = query.selected_columns[0]
            for key, i, name in await session.execute(query.where(column.in_(chunk), seen)):
                found[key] = (i, name, alias)
    return found


async def like(
    session: AsyncSession, name: str, seen: ColumnElement[bool], limit: int = 3
) -> list[tuple[uuid.UUID, str]]:
    """Ingredients named like a name nothing matches, by it or another name,
    closest first: "sweet rice flower" finds "Glutinous Rice Flour" by its
    alias "Sweet Rice Flour"."""
    closeness = func.greatest(
        func.similarity(Ingredient.name, name),
        func.coalesce(
            select(func.max(func.similarity(IngredientAlias.name, name)))
            .where(IngredientAlias.ingredient_id == Ingredient.id)
            .scalar_subquery(),
            0,
        ),
    )
    # The % operator is the trigram indexes' way in.
    by_alias = select(IngredientAlias.ingredient_id).where(IngredientAlias.name.op("%")(name))
    rows = await session.execute(
        select(Ingredient.id, Ingredient.name)
        .where(or_(Ingredient.name.op("%")(name), Ingredient.id.in_(by_alias)), seen)
        .order_by(closeness.desc(), Ingredient.name)
        .limit(limit)
    )
    return [(i, n) for i, n in rows]


# Fixing the list. An ingredient a line was matched to wrongly is fixed on
# the recipe, by correcting the line; these fix the ingredient itself.


class Taken(Exception):
    """The name is another ingredient's, or another name for one: merge."""

    def __init__(self, ingredient: Ingredient) -> None:
        super().__init__(ingredient.name)
        self.ingredient = ingredient


class InUse(Exception):
    """Something still points at the ingredient, so it can't be deleted."""


async def rename(session: AsyncSession, ingredient: Ingredient, name: str) -> None:
    """Rename an ingredient. If that changes its key, the old name stays as
    an alias, so lines written that way still find it."""
    name = " ".join(name.split())
    key = match_key(name)
    if not key:
        raise ValueError("A name needs at least one letter or number.")
    if key != ingredient.match_key:
        holder = (await _ids(session, {key})).get(key)
        if holder is not None and holder != ingredient.id:
            raise Taken(await session.get_one(Ingredient, holder))
        # Its own alias, if it was one, is its name now.
        await session.execute(
            delete(IngredientAlias).where(
                IngredientAlias.match_key == key, IngredientAlias.region.is_(None)
            )
        )
        session.add(
            IngredientAlias(
                ingredient_id=ingredient.id, name=ingredient.name, match_key=ingredient.match_key
            )
        )
        ingredient.match_key = key
    ingredient.name = name
    await session.flush()


async def merge(session: AsyncSession, source: Ingredient, target: Ingredient) -> None:
    """Fold one ingredient into another: everything that used it uses the
    other, and its name and aliases become the other's aliases."""
    if source.id == target.id:
        raise ValueError("An ingredient can't be merged into itself.")
    s, t = source.id, target.id
    await session.execute(
        update(IngredientOption).where(IngredientOption.ingredient_id == s).values(ingredient_id=t)
    )
    # Aliases can't clash: a name means one ingredient in each region.
    await session.execute(
        update(IngredientAlias).where(IngredientAlias.ingredient_id == s).values(ingredient_id=t)
    )
    # People's larders keep what they have, under the name kept.
    await session.execute(
        update(LarderItem).where(LarderItem.ingredient_id == s).values(ingredient_id=t)
    )
    await _merge_substitutions(session, s, t)
    await session.execute(
        update(Ingredient).where(Ingredient.parent_id == s, Ingredient.id != t).values(parent_id=t)
    )
    if target.parent_id == s:
        target.parent_id = source.parent_id if source.parent_id != t else None
    session.add(IngredientAlias(ingredient_id=t, name=source.name, match_key=source.match_key))
    # Its links to FoodData Central and Wikidata, where the other has none.
    if target.fdc_id is None:
        target.fdc_id = source.fdc_id
    if target.wikidata_id is None:
        target.wikidata_id, target.wikidata_label = source.wikidata_id, source.wikidata_label
    await session.delete(source)
    await session.flush()


async def _merge_substitutions(session: AsyncSession, s: uuid.UUID, t: uuid.UUID) -> None:
    """Move swaps from one ingredient to the other, dropping the ones that
    would swap it for itself and the ones the other already has."""
    sub = Substitution
    await session.execute(
        delete(sub).where(
            or_(
                and_(sub.from_ingredient_id == s, sub.to_ingredient_id == t),
                and_(sub.from_ingredient_id == t, sub.to_ingredient_id == s),
            )
        )
    )
    for side in ("from_ingredient_id", "to_ingredient_id"):
        # The columns uq_substitutions_swap compares, besides this side.
        twin = aliased(sub)
        same = [
            getattr(twin, c).is_not_distinct_from(getattr(sub, c)) for c in _SWAP_KEY if c != side
        ]
        await session.execute(
            delete(sub).where(
                getattr(sub, side) == s, exists().where(getattr(twin, side) == t, *same)
            )
        )
        await session.execute(update(sub).where(getattr(sub, side) == s).values({side: t}))


_SWAP_KEY = (
    "from_ingredient_id",
    "from_recipe_id",
    "to_ingredient_id",
    "to_recipe_id",
    "diet_tag_id",
    "source_edition_id",
)


def family(*ingredient_ids: uuid.UUID, name: str = "family"):
    """The ingredients and everything under them, as a select of IDs. UNION,
    not UNION ALL, so a loop in the hierarchy still ends; set_parent makes
    none, but rows written another way could."""
    tree = (
        select(Ingredient.id)
        .where(Ingredient.id.in_(ingredient_ids))
        .cte(name=name, recursive=True)
    )
    tree = tree.union(select(Ingredient.id).where(Ingredient.parent_id == tree.c.id))
    return select(tree.c.id)


def rooted_family(*ingredient_ids: uuid.UUID, name: str = "rooted"):
    """As family, but each row says which of the given ingredients it is
    under (root, id), so a match on cheddar counts as a match on cheese."""
    tree = (
        select(Ingredient.id.label("root"), Ingredient.id.label("id"))
        .where(Ingredient.id.in_(ingredient_ids))
        .cte(name=name, recursive=True)
    )
    return tree.union(select(tree.c.root, Ingredient.id).where(Ingredient.parent_id == tree.c.id))


def rooted_ancestry(*ingredient_ids: uuid.UUID, name: str = "ancestry"):
    """The other way from rooted_family: each ingredient and everything above
    it, (root, id), so having Chipotle Hot Sauce counts as having Hot Sauce
    (the larder; Ray, 2026-11-10), but not the other way round."""
    tree = (
        select(Ingredient.id.label("root"), Ingredient.id.label("id"))
        .where(Ingredient.id.in_(ingredient_ids))
        .cte(name=name, recursive=True)
    )
    above = aliased(Ingredient)
    return tree.union(
        select(tree.c.root, above.parent_id)
        .select_from(above)
        .where(above.id == tree.c.id, above.parent_id.is_not(None))
    )


async def set_parent(
    session: AsyncSession, ingredient: Ingredient, parent: Ingredient | None
) -> None:
    """Put an ingredient under another (cheddar under cheese), or under
    nothing. Refused if that would make a loop."""
    if parent is not None:
        below = set(await session.scalars(family(ingredient.id)))
        if parent.id == ingredient.id:
            raise ValueError("An ingredient can't go under itself.")
        if parent.id in below:
            raise ValueError(
                f"“{parent.name}” comes under “{ingredient.name}”, so it can't go above it."
            )
    ingredient.parent_id = parent.id if parent else None
    await session.flush()


async def remove(session: AsyncSession, ingredient: Ingredient) -> None:
    """Delete an ingredient nothing uses; its aliases go with it."""
    i = ingredient.id
    used = await session.scalar(
        select(
            exists().where(IngredientOption.ingredient_id == i)
            | exists().where(
                or_(Substitution.from_ingredient_id == i, Substitution.to_ingredient_id == i)
            )
            | exists().where(Ingredient.parent_id == i)
        )
    )
    if used:
        raise InUse(ingredient.name)
    await session.delete(ingredient)
    await session.flush()


def _chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
