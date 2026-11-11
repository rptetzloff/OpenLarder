"""Possible typos in ingredient names: "Lemon Jucie" for "Lemon Juice".

*Ray, 2026-11-10: flag everything.* Nothing is changed by itself: a rare
name close to a much commoner one is flagged on each recipe using it, with
the commoner one suggested, and a person changes it in one click or
dismisses the flag. Measured over the household index (6,953 names), no rule
was safe to apply unasked: swapped letters were 9 real typos in 10 ("Crema"
is not "Cream"), and one letter off found as many real ingredients as
typos ("Bitters" and "Butter", "Custard" and "Mustard Powder", "Culantro"
and "Cilantro").

Two names are compared by their match keys (ingredients.match_key), word by
word: the same words but one, and that one

- two letters swapped ("jucie", "juice"), in a word of 4 letters or more; or
- one letter off, in a word of 5 or more; or two, in a word of 8 or more;

and the commoner name used at least TIMES_MORE as often. Except for a swap,
the rare name is used at most RARE_USES times: one letter off with both
names in common use is two ingredients ("Beef" and "Beet"). That suggests
53 names in the household index, 49 of them used once or twice.

Only the public catalog is compared, and only its recipes flagged: a family
collection's names are its own.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import lines
from openlarder.models import (
    FlagKind,
    Ingredient,
    IngredientOption,
    Recipe,
    RecipeFlag,
    RecipeIngredient,
    Source,
)

RARE_USES = 2
TIMES_MORE = 5
ARROW = " → "


def _distance(a: str, b: str, limit: int = 2) -> int:
    """Edits between two words, a swap of neighbours counting as one; past
    limit, limit + 1, worked out no further (most pairs a sweep compares
    are far apart)."""
    far = limit + 1
    if abs(len(a) - len(b)) > limit:
        return far
    d = [[far] * (len(b) + 1) for _ in range(len(a) + 1)]
    for j in range(min(len(b), limit) + 1):
        d[0][j] = j
    before = 0
    for i in range(1, len(a) + 1):
        if i <= limit:
            d[i][0] = i
        low = d[i][0]
        for j in range(max(1, i - limit), min(len(b), i + limit) + 1):
            cell = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cell = min(cell, d[i - 2][j - 2] + 1)
            d[i][j] = cell
            low = min(low, cell)
        # A swap reaches back two rows, so both must be past the limit.
        if low > limit and before > limit:
            return far
        before = low
    return min(d[len(a)][len(b)], far)


def _swapped(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return (
        len(diff) == 2
        and diff[1] == diff[0] + 1
        and (a[diff[0]], a[diff[1]]) == (b[diff[1]], b[diff[0]])
    )


def close(rare: str, common: str, rare_uses: int, common_uses: int) -> bool:
    """Whether the rare key looks like a typo of the common one."""
    if common_uses < TIMES_MORE * rare_uses:
        return False
    x, y = rare.split(), common.split()
    if len(x) != len(y):
        return False
    differ = [i for i in range(len(x)) if x[i] != y[i]]
    if len(differ) != 1:
        return False
    a, b = x[differ[0]], y[differ[0]]
    if _swapped(a, b):
        return len(b) >= 4
    # Cheap refusals first: the edit distance is most of a sweep's time.
    if rare_uses > RARE_USES or len(b) < 5 or abs(len(a) - len(b)) > (2 if len(b) >= 8 else 1):
        return False
    distance = _distance(a, b)
    return (distance == 1 and len(b) >= 5) or (distance == 2 and len(b) >= 8)


@dataclass(frozen=True)
class Named:
    id: uuid.UUID
    key: str
    name: str
    uses: int


def suggest(named: list[Named]) -> dict[uuid.UUID, Named]:
    """For each name that looks like a typo, the one it's likely meant to be:
    a swap first, then the most used."""
    # By the words around the one that differs, and that word's length: a
    # name is compared only with names it could be one edit or two from.
    index: dict[tuple, list[Named]] = defaultdict(list)
    for n in named:
        words = n.key.split()
        for i in range(len(words)):
            index[(len(words), i, tuple(words[:i]), tuple(words[i + 1 :]), len(words[i]))].append(n)
    found: dict[uuid.UUID, Named] = {}
    for n in named:
        words = n.key.split()
        best: tuple[bool, int, Named] | None = None
        for i in range(len(words)):
            around = (len(words), i, tuple(words[:i]), tuple(words[i + 1 :]))
            for length in range(len(words[i]) - 2, len(words[i]) + 3):
                for other in index.get((*around, length), ()):
                    if other is n or other.uses < TIMES_MORE * n.uses:
                        continue
                    if not close(n.key, other.key, n.uses, other.uses):
                        continue
                    rank = (_swapped(words[i], other.key.split()[i]), other.uses, other)
                    if best is None or rank[:2] > best[:2]:
                        best = rank
        if best:
            found[n.id] = best[2]
    return found


def _public():
    return (
        Recipe.review == "published",
        Source.review == "published",
        Source.private.is_(False),
    )


async def sweep(session: AsyncSession) -> list[tuple[uuid.UUID, str]]:
    """Flag every public recipe using a name that looks like a typo, once:
    a flag dismissed stays dismissed. Returns the new flags (recipe, detail)."""
    used = await session.execute(
        select(
            Ingredient.id,
            Ingredient.match_key,
            Ingredient.name,
            func.count(func.distinct(IngredientOption.recipe_id)),
        )
        .join(IngredientOption, IngredientOption.ingredient_id == Ingredient.id)
        .join(Recipe, Recipe.id == IngredientOption.recipe_id)
        .join(Source, Source.id == Recipe.source_id)
        .where(*_public())
        .group_by(Ingredient.id)
    )
    meant = suggest([Named(i, k, n, c) for i, k, n, c in used])
    if not meant:
        return []
    rows = await session.execute(
        select(
            IngredientOption.recipe_id,
            IngredientOption.ingredient_id,
            IngredientOption.rank,
            RecipeIngredient.original_text,
        )
        .join(RecipeIngredient, RecipeIngredient.id == IngredientOption.recipe_ingredient_id)
        .join(Recipe, Recipe.id == IngredientOption.recipe_id)
        .join(Source, Source.id == Recipe.source_id)
        .where(IngredientOption.ingredient_id.in_(list(meant)), *_public())
    )
    wanted: set[tuple[uuid.UUID, str]] = set()
    for recipe_id, ingredient_id, rank, text in rows:
        read = lines.options(text)
        if rank <= len(read):
            wanted.add((recipe_id, f"{read[rank - 1].name}{ARROW}{meant[ingredient_id].name}"))
    raised = []
    for recipe_id, detail in sorted(wanted):
        if await session.scalar(
            select(
                exists().where(
                    RecipeFlag.recipe_id == recipe_id,
                    RecipeFlag.kind == FlagKind.POSSIBLE_TYPO.value,
                    RecipeFlag.detail == detail,
                )
            )
        ):
            continue
        session.add(
            RecipeFlag(recipe_id=recipe_id, kind=FlagKind.POSSIBLE_TYPO.value, detail=detail)
        )
        raised.append((recipe_id, detail))
    await session.flush()
    return raised


def parse(detail: str | None) -> tuple[str, str] | None:
    """A possible-typo flag's (as written, suggested)."""
    if not detail or ARROW not in detail:
        return None
    written, _, meant = detail.partition(ARROW)
    return (written, meant) if written and meant else None


def corrected(text: str, written: str, meant: str) -> str | None:
    """The line with the option written so changed to the one meant; None if
    no option of the line is written so."""
    if not any(o.name == written for o in lines.options(text)):
        return None
    pattern = re.compile(rf"(?<!\w){re.escape(written)}(?!\w)")
    fixed = pattern.sub(meant.replace("\\", "\\\\"), text, count=1)
    return fixed if fixed != text else None
