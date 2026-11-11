"""Suggesting the FoodData Central food, and the Wikidata item, an
ingredient is probably the same as (models/foods.LinkSuggestion), for a
moderator to accept or dismiss. Nothing is linked by itself: close names
are often different foods, as with typos (typos.py).

**FDC.** Words are compared as ingredients.match_key makes them, so
"Onions" is "Onion". A food fits a name when

- every word of the name is in the food's description;
- the description's first part (before the first comma; after it, for a
  category first: "Spices, cinnamon, ground") is among the name's words,
  in the name's order if it's two words or more ("Chocolate milk" isn't
  "Milk Chocolate");
- no word it has more says it's something else ("meatless", "imitation",
  "canned", "no": NEGATING).

It's *likely* when it has no word more than the name but plain ones
(NEUTRAL: "raw", "fresh", "NFS"...), *unsure* with one; with more, none is
suggested. Among those that fit, the fewest words more, then Foundation
over SR Legacy over the survey's, then the shortest.

Measured on the household index (2026-11-11; 6,953 names, 13,694 foods):
of the 1,000 most used names, 355 likely and 74 unsure, covering 58% and
63% of ingredient uses; 940 suggestions in all. The likely ones read right
but for a handful.

**Wikidata.** Through SR Legacy's NDB numbers, which some 1,470 Wikidata
items cite (P1978): an ingredient's likely SR Legacy foods with one.
Always *unsure*: the item is often the plant ("Brassica napus" for canola
oil) or something else (kale's NDB number is on "lutein"). About 110 of the
1,000 most used names.
"""

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

import httpx2
from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import ingredients, visibility, wikidata
from openlarder.models import FdcFood, Ingredient, IngredientOption, LinkSuggestion

_stems: dict[str, str] = {}


def _stem(word: str) -> str:
    if word not in _stems:
        _stems[word] = ingredients.match_key(word) or word
    return _stems[word]


def words(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())]


def _set(*raw: str) -> frozenset[str]:
    return frozenset(w for r in raw for w in words(r))


# Words FDC adds that say nothing against a match.
NEUTRAL = _set(
    "raw", "fresh", "all", "commercial", "regular", "plain", "whole", "includes", "u s",
    "usda", "and", "with", "or", "in", "nfs", "solid", "unprepared", "uncooked", "dry", "100",
)  # fmt: skip
# A category first: the food is the next part.
CATEGORY_HEADS = {" ".join(words(h)) for h in ("Spices", "Spice", "Leavening agents")}
# After "Spices": how a spice is sold, not another spice.
SPICE_NEUTRAL = _set("ground", "dried")
# A food with one of these more than the name is something else.
NEGATING = _set(
    "meatless", "imitation", "substitute", "no", "without", "free", "nonfat", "lowfat", "low",
    "reduced", "light", "diet", "artificial", "vegetarian", "baby", "babyfood", "infant",
    "toddler", "frozen", "canned", "fried", "breaded", "pickled", "flavored", "sweetened",
    "candied", "glazed", "roasted", "dehydrated", "instant", "mix", "prepared", "restaurant",
    "fast", "school",
)  # fmt: skip
RANK = {"foundation_food": 0, "sr_legacy_food": 1, "survey_fndds_food": 2}


@dataclass(frozen=True)
class Prepared:
    food: FdcFood
    head: tuple[str, ...]
    all: frozenset[str]
    neutral: frozenset[str]


@dataclass(frozen=True)
class Match:
    food: FdcFood
    extra: int

    @property
    def certainty(self) -> str:
        return "likely" if self.extra == 0 else "unsure"


class Foods:
    """FDC's foods, read for matching, by word."""

    def __init__(self, foods: Iterable[FdcFood]) -> None:
        self.by_word: dict[str, list[Prepared]] = defaultdict(list)
        for food in foods:
            parts = [words(p) for p in food.description.split(",")]
            neutral = NEUTRAL
            if len(parts) > 1 and " ".join(parts[0]) in CATEGORY_HEADS:
                parts = parts[1:]
                neutral = NEUTRAL | SPICE_NEUTRAL
            every = frozenset(w for p in parts for w in p)
            item = Prepared(food, tuple(parts[0]) if parts else (), every, neutral)
            for w in every:
                self.by_word[w].append(item)

    def matches(self, name: str) -> list[Match]:
        """The foods that fit the name, best first."""
        mine = words(name)
        if not mine:
            return []
        have = set(mine)
        out = []
        for p in self.by_word.get(mine[-1], ()):
            if not have <= p.all or not set(p.head) <= have | p.neutral:
                continue
            head = [w for w in p.head if w not in p.neutral]
            if len(head) > 1 and f" {' '.join(head)} " not in f" {' '.join(mine)} ":
                continue
            extra = [w for w in p.all if w not in have and w not in p.neutral]
            if len(extra) > 1 or any(w in NEGATING for w in extra):
                continue
            out.append(Match(p.food, len(extra)))
        out.sort(key=lambda m: (m.extra, RANK[m.food.data_type], len(m.food.description)))
        return out


@dataclass
class Suggested:
    fdc: int
    wikidata: int


async def suggest(
    session: AsyncSession, transport: httpx2.AsyncBaseTransport | None = None
) -> Suggested:
    """Suggest a food and an item for every public ingredient without one,
    and without one open already; what was dismissed for an ingredient
    isn't suggested again, the next best is. The caller commits."""
    foods = Foods(await session.scalars(select(FdcFood)))
    rows = (
        await session.execute(
            select(Ingredient.id, Ingredient.name, Ingredient.fdc_id, Ingredient.wikidata_id)
            .where(
                visibility.ingredients_seen_by(None),
                (Ingredient.fdc_id.is_(None)) | (Ingredient.wikidata_id.is_(None)),
                exists().where(IngredientOption.ingredient_id == Ingredient.id),
            )
            .order_by(Ingredient.name)
        )
    ).all()
    taken: dict[tuple, set] = defaultdict(set)
    busy: set[tuple] = set()
    for ingredient_id, source, fdc_id, item, status in await session.execute(
        select(
            LinkSuggestion.ingredient_id,
            LinkSuggestion.source,
            LinkSuggestion.fdc_id,
            LinkSuggestion.wikidata_id,
            LinkSuggestion.status,
        )
    ):
        taken[(ingredient_id, source)].add(fdc_id if source == "fdc" else item)
        if status == "open":
            busy.add((ingredient_id, source))
    by_ndb: dict[int, wikidata.Label] | None = None
    new: list[dict] = []
    for ingredient_id, name, fdc_id, item in rows:
        found = foods.matches(name)
        if fdc_id is None and (ingredient_id, "fdc") not in busy:
            fresh = [m for m in found if m.food.fdc_id not in taken[(ingredient_id, "fdc")]]
            if fresh:
                new.append(
                    {
                        "ingredient_id": ingredient_id,
                        "source": "fdc",
                        "fdc_id": fresh[0].food.fdc_id,
                        "certainty": fresh[0].certainty,
                    }
                )
        if item is None and (ingredient_id, "wikidata") not in busy:
            numbered = [m for m in found if m.extra == 0 and m.food.ndb_number is not None]
            if not numbered:
                continue
            if by_ndb is None:
                by_ndb = await wikidata.by_ndb(transport)
            for m in numbered:
                label = by_ndb.get(m.food.ndb_number)
                if label and label.wikidata_id not in taken[(ingredient_id, "wikidata")]:
                    new.append(
                        {
                            "ingredient_id": ingredient_id,
                            "source": "wikidata",
                            "wikidata_id": label.wikidata_id,
                            "label": label.label,
                            "certainty": "unsure",
                        }
                    )
                    break
    blank = {"fdc_id": None, "wikidata_id": None, "label": None}
    new = [blank | n for n in new]
    for i in range(0, len(new), 1000):
        await session.execute(
            insert(LinkSuggestion).values(new[i : i + 1000]).on_conflict_do_nothing()
        )
    return Suggested(
        fdc=sum(1 for n in new if n["source"] == "fdc"),
        wikidata=sum(1 for n in new if n["source"] == "wikidata"),
    )


async def uses(session: AsyncSession, ids: Iterable) -> dict:
    """Recipes using each ingredient, public ones."""
    return dict(
        (
            await session.execute(
                select(
                    IngredientOption.ingredient_id,
                    func.count(func.distinct(IngredientOption.recipe_id)),
                )
                .where(
                    IngredientOption.ingredient_id.in_(list(ids)),
                    visibility.options_seen_by(None),
                )
                .group_by(IngredientOption.ingredient_id)
            )
        ).all()
    )
