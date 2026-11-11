"""Other names for ingredients, and broader ingredients, from the Wikidata
items they're linked to, suggested for a person to decide (TODO.md,
Ingredient data: "using them"). Nothing changes by itself.

For each public ingredient linked to an item:

- **Other names.** The item's English aliases, and its British English
  label as a UK name ("aubergine" for eggplant). Only plain common names:
  all lower case, which leaves out the scientific and proper names Wikidata
  capitalises ("Allium cepa L.", "Mel"), and none naming the plant ("onion
  plant"). Suggested on Admin › Ingredient links, one at a time: many are
  true but no use ("domesticated carrot").
- **The same ingredient.** A name another of our ingredients already has
  (an ingredient "Aubergine" beside "Eggplant") is a merge, suggested in
  the Suggestions queue, keeping the linked one's name.
- **Broader.** When the item is a kind of (P279) another item an ingredient
  is linked to, that one above it, suggested in the Suggestions queue, for
  an ingredient with nothing above it yet.

Merges and parents use the queue's own kinds, so accepting them is the
same merge or set-parent as anywhere else, with its checks.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass

import httpx2
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import ingredients, visibility, wikidata
from openlarder.models import (
    Ingredient,
    IngredientAlias,
    IngredientOption,
    LinkSuggestion,
    Suggestion,
)

MODEL = "wikidata"
VERSION = "wikidata-names-v1"
_PLAIN = re.compile(r"[^\W\d_]+(?:[ '\-][^\W\d_]+)*")


def plain(name: str) -> bool:
    """A common name: lower case, letters, one or a few words."""
    return (
        name == name.lower()
        and len(name) <= 60
        and _PLAIN.fullmatch(name) is not None
        and "plant" not in name.split()
    )


@dataclass
class Suggested:
    names: int
    merges: int
    parents: int


def _pair(a: uuid.UUID, b: uuid.UUID) -> list[str]:
    # The queue's target: the two ids, the lower first.
    return sorted([str(a), str(b)])


async def suggest(
    session: AsyncSession, transport: httpx2.AsyncBaseTransport | None = None
) -> Suggested:
    """Suggest other names, merges and broader ingredients from every
    linked public ingredient's item. The caller commits."""
    linked = (
        await session.execute(
            select(
                Ingredient.id,
                Ingredient.name,
                Ingredient.match_key,
                Ingredient.wikidata_id,
                Ingredient.parent_id,
            ).where(
                Ingredient.wikidata_id.is_not(None),
                visibility.ingredients_seen_by(None),
                exists().where(IngredientOption.ingredient_id == Ingredient.id),
            )
        )
    ).all()
    if not linked:
        return Suggested(0, 0, 0)
    by_item: dict[str, list] = defaultdict(list)
    for row in linked:
        by_item[row.wikidata_id].append(row)
    found = await wikidata.names(list(by_item), transport)

    # What's there already: each ingredient's aliases, and the names taken.
    wanted: set[str] = set()
    for n in found.values():
        wanted |= {ingredients.match_key(a) for a in n.aliases | ({n.uk} if n.uk else set())}
    wanted.discard("")
    owners = await ingredients.known_ids(session, wanted)
    public = set(
        await session.scalars(
            select(Ingredient.id).where(
                Ingredient.id.in_(set(owners.values())), visibility.ingredients_seen_by(None)
            )
        )
    )
    theirs: dict[uuid.UUID, set[tuple[str, str | None]]] = defaultdict(set)
    uk_taken: set[str] = set()
    for ingredient_id, key, name, region in await session.execute(
        select(
            IngredientAlias.ingredient_id,
            IngredientAlias.match_key,
            IngredientAlias.name,
            IngredientAlias.region,
        ).where(
            (IngredientAlias.ingredient_id.in_([r.id for r in linked]))
            | (IngredientAlias.region == "UK")
        )
    ):
        theirs[ingredient_id].add((key, region))
        if region == "UK":
            uk_taken.add(name.lower())
    decided = {
        (kind, tuple(target))
        for kind, target in await session.execute(
            select(Suggestion.kind, Suggestion.target).where(
                Suggestion.model == MODEL, Suggestion.kind.in_(("merge", "parent"))
            )
        )
    }

    names: list[dict] = []
    queue: list[dict] = []
    for row in linked:
        item = found.get(row.wikidata_id)
        if item is None:
            continue
        offered = [(a, None) for a in sorted(item.aliases)]
        if item.uk and item.uk.lower() != (item.label or "").lower():
            offered.append((item.uk, "UK"))
        for name, region in offered:
            key = ingredients.match_key(name)
            if not plain(name) or not key or key == row.match_key:
                continue
            if (key, region) in theirs[row.id] or (key, None) in theirs[row.id]:
                continue
            owner = owners.get(key)
            if owner is not None and owner != row.id:
                if owner in public and ("merge", tuple(_pair(row.id, owner))) not in decided:
                    other = await session.get(Ingredient, owner)
                    queue.append(
                        {
                            "kind": "merge",
                            "target": _pair(row.id, owner),
                            "proposal": {
                                "a_id": str(row.id),
                                "b_id": str(owner),
                                "a_name": row.name,
                                "b_name": other.name,
                                "decision": "same",
                                "keep_name": "a",
                                "certainty": "likely",
                            },
                            "reason": (
                                f"Wikidata calls {row.name}'s item ({row.wikidata_id})"
                                f" “{name}” too."
                            ),
                        }
                    )
                    decided.add(("merge", tuple(_pair(row.id, owner))))
                continue
            if owner == row.id or (region == "UK" and name.lower() in uk_taken):
                continue
            names.append(
                {
                    "ingredient_id": row.id,
                    "source": "alias",
                    "fdc_id": None,
                    "wikidata_id": row.wikidata_id,
                    "label": item.label,
                    "alias": name,
                    "region": region,
                    "certainty": "unsure",
                }
            )
        if row.parent_id is None:
            for parent_item in sorted(item.parents):
                for above in by_item.get(parent_item, ()):
                    pair = ("parent", tuple(_pair(row.id, above.id)))
                    if above.id == row.id or pair in decided:
                        continue
                    queue.append(
                        {
                            "kind": "parent",
                            "target": _pair(row.id, above.id),
                            "proposal": {
                                "a_id": str(row.id),
                                "b_id": str(above.id),
                                "a_name": row.name,
                                "b_name": above.name,
                                "decision": "a_under_b",
                                "certainty": "likely",
                            },
                            "reason": (
                                f"On Wikidata, {row.name}'s item ({row.wikidata_id}) is a kind"
                                f" of {above.name}'s ({parent_item})."
                            ),
                        }
                    )
                    decided.add(pair)

    added_names = 0
    if names:
        result = await session.execute(
            insert(LinkSuggestion)
            .values(names)
            .on_conflict_do_nothing()
            .returning(LinkSuggestion.id)
        )
        added_names = len(result.all())
    added = {"merge": 0, "parent": 0}
    for q in queue:
        result = await session.execute(
            insert(Suggestion)
            .values(**q, model=MODEL, prompt_version=VERSION)
            .on_conflict_do_nothing()
            .returning(Suggestion.id)
        )
        if result.first() is not None:
            added[q["kind"]] += 1
    return Suggested(names=added_names, merges=added["merge"], parents=added["parent"])
