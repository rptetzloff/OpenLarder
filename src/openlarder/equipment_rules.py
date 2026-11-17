"""Equipment a recipe probably needs, read off its title, its tags and its
book: suggestions for a moderator, never a need added unasked.

*Ray's equipment spec, 2026-11-15*, which asked for "a rules file like
`title_rules.py`", and, asked whether he wanted the queue at all, *Ray,
2026-11-15: yes*. Most of the catalog was indexed before equipment was
recorded, and nobody will go back through it by hand. A rule knows one
thing: "Peach Gelato" wants an ice cream maker. It doesn't know the rest
of what the recipe needs, and it is sometimes wrong: in the spec's words,
"'Grilled cheese' does not need a grill". So each goes to the Suggestions
queue (routers/suggestions.py), where a moderator accepts it, which adds
the need as an edit of theirs and leaves the recipe's equipment not said
to be whole, or dismisses it, after which it isn't suggested for that
recipe again.

**A recipe's title** (TITLE): words that name a thing, or a dish made in
one. Whole words, in any case, with or without a plural "s": "waffle"
is found in "Waffles" and not in "Waffled"; "smoked" not in "Smoker".

**A recipe's tags** (TAGS): its own and its source's, by name. A
technique named for a thing is that thing.

**Its source** (SOURCE): a book titled for one appliance suggests it for
every recipe in it, as the spec has it. Only the appliances a whole book
is about; a book called "Ice Cream" has a chapter of sauces.

What these can't see: a recipe that needs a thing its title doesn't name;
a thing named for another reason ("Grilled Cheese", "Smoked Paprika
Chicken", "Canned Tomato Soup"); a title in another language. The names
on the right are the equipment list's as it was seeded (migration 0079):
one renamed since is found by its old name, which is kept as another name
for it, and one deleted or marked as any kitchen's suggests nothing.
"""

import re
import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import equipment as kit
from openlarder import needs, visibility
from openlarder.ingredients import match_key
from openlarder.models import (
    Equipment,
    EquipmentOption,
    Recipe,
    RecipeTag,
    Source,
    SourceTag,
    Suggestion,
    Tag,
)

MODEL = "rules"
VERSION = "equipment-rules-v1"
KIND = "equipment"

# The equipment, and the words of a recipe's title that suggest it.
TITLE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Ice cream maker", ("ice cream", "gelato", "sorbet")),
    ("Waffle iron", ("waffle",)),
    ("Sous vide circulator", ("sous vide",)),
    ("Smoker", ("smoked",)),
    ("Grill", ("grilled",)),
    ("Bundt pan", ("bundt",)),
    ("Slow cooker", ("slow cooker",)),
    ("Multicooker", ("instant pot",)),
    ("Pressure cooker", ("pressure cooker",)),
    ("Air fryer", ("air fryer",)),
    ("Canning pot", ("canned", "preserves")),
    ("Pasta machine", ("fresh pasta",)),
)
# The technique tags named for a thing (the tag list as seeded).
TAGS: dict[str, str] = {
    "Grilling": "Grill",
    "Pressure Cooker": "Pressure cooker",
    "Slow Cooker": "Slow cooker",
    "Smoking": "Smoker",
    "Sous Vide": "Sous vide circulator",
}
# The appliances a whole book is about, and the words of its title.
SOURCE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Slow cooker", ("slow cooker",)),
    ("Multicooker", ("instant pot", "multicooker")),
    ("Pressure cooker", ("pressure cooker",)),
    ("Air fryer", ("air fryer",)),
    ("Sous vide circulator", ("sous vide",)),
    ("Bread machine", ("bread machine",)),
)


def _found(words: str, text: str) -> bool:
    """The words in the text: whole, in any case, the last with or without a
    plural "s", and any run of spaces or hyphens between them ("air-fryer",
    "sous-vide")."""
    parts = [re.escape(w) for w in words.split()]
    pattern = r"\b" + r"[\s\-]+".join(parts) + r"s?\b"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _by_words(rules: Iterable[tuple[str, tuple[str, ...]]], text: str) -> dict[str, str]:
    """Each thing the text suggests, with the first of its words found."""
    out: dict[str, str] = {}
    for thing, phrases in rules:
        said = next((p for p in phrases if _found(p, text)), None)
        if said is not None:
            out[thing] = said
    return out


# How a reason begins when it's the recipe's source that says so, by its
# title or a tag: every recipe of that source is suggested the same thing,
# and a moderator may accept them together (routers/suggestions.py). Read
# off the reason, so it's true of the suggestions filed before this was
# asked of them.
OF_ITS_SOURCE = "Its source"


def of_its_source(reason: str | None) -> bool:
    return bool(reason) and reason.startswith(OF_ITS_SOURCE)


def suggested(
    title: str,
    tags: Iterable[str] = (),
    source_title: str | None = None,
    source_tags: Iterable[str] = (),
) -> dict[str, str]:
    """The equipment a recipe's title, tags and source suggest, by the
    equipment list's name for it, each with why in a sentence to show. The
    recipe's own title is the reason given when several things say so, then
    its tags, then its source."""
    out: dict[str, str] = {}
    for thing, said in _by_words(TITLE, title).items():
        out[thing] = f"Its title says “{said}”."
    for tag in tags:
        if tag in TAGS:
            out.setdefault(TAGS[tag], f"It is tagged {tag}.")
    for tag in source_tags:
        if tag in TAGS:
            out.setdefault(TAGS[tag], f"Its source is tagged {tag}.")
    if source_title:
        for thing, said in _by_words(SOURCE, source_title).items():
            out.setdefault(thing, f"Its source's title says “{said}”.")
    return out


async def sweep(
    session: AsyncSession,
    recipes: Sequence[uuid.UUID] | None = None,
    sources: Sequence[uuid.UUID] | None = None,
) -> int:
    """Add a suggestion for each thing these rules say a recipe probably
    needs (recipes: just these; sources: just the recipes of these); how
    many were new. The caller commits.

    Only recipes anyone can see: one in a private collection, or waiting
    for review, never reaches the queue. Not one whose equipment someone
    has said is whole (a need or "nothing special", saved by a person):
    they've looked, and a rule knows less than they do. Not a thing the
    recipe already needs, or something that counts as it. And not one
    already accepted or dismissed for that recipe."""
    wanted = (
        select(Recipe.id, Recipe.title, Source.id, Source.title)
        .join(Source, Source.id == Recipe.source_id)
        .where(visibility.recipes_seen_by(None), Recipe.equipment_checked.is_(False))
    )
    if recipes is not None:
        wanted = wanted.where(Recipe.id.in_(recipes))
    if sources is not None:
        wanted = wanted.where(Recipe.source_id.in_(sources))
    rows = (await session.execute(wanted)).all()
    if not rows:
        return 0
    own_tags: dict[uuid.UUID, list[str]] = {}
    for recipe_id, name in await session.execute(
        select(RecipeTag.recipe_id, Tag.name)
        .join(Tag, Tag.id == RecipeTag.tag_id)
        .where(Tag.name.in_(TAGS), RecipeTag.recipe_id.in_([r[0] for r in rows]))
    ):
        own_tags.setdefault(recipe_id, []).append(name)
    source_tags: dict[uuid.UUID, list[str]] = {}
    for source_id, name in await session.execute(
        select(SourceTag.source_id, Tag.name)
        .join(Tag, Tag.id == SourceTag.tag_id)
        .where(Tag.name.in_(TAGS), SourceTag.source_id.in_({r[2] for r in rows}))
    ):
        source_tags.setdefault(source_id, []).append(name)
    found: dict[uuid.UUID, tuple[str, dict[str, str]]] = {}
    for recipe_id, title, source_id, source_title in rows:
        said = suggested(
            title, own_tags.get(recipe_id, ()), source_title, source_tags.get(source_id, ())
        )
        if said:
            found[recipe_id] = (title, said)
    if not found:
        return 0
    # Each name the rules use, as the list has it now: the thing of that
    # name, or the one it's another name for; none if it has gone, and not
    # one marked as any kitchen's or taken off the list since.
    things: dict[str, Equipment] = {}
    covers: dict[str, set[uuid.UUID]] = {}
    for name in {n for _, said in found.values() for n in said}:
        held = await needs.held_by(session, match_key(name))
        if held is None or held[0].assumed or not held[0].listed:
            continue
        things[name] = held[0]
        covers[name] = set(
            await session.scalars(kit.family(held[0].id, name=f"rule_{len(covers)}"))
        )
    has: dict[uuid.UUID, set[uuid.UUID]] = {}
    for recipe_id, equipment_id in await session.execute(
        select(EquipmentOption.recipe_id, EquipmentOption.equipment_id).where(
            EquipmentOption.recipe_id.in_(found)
        )
    ):
        has.setdefault(recipe_id, set()).add(equipment_id)
    decided = {
        (p.get("recipe_id"), p.get("equipment_id"))
        for (p,) in await session.execute(
            select(Suggestion.proposal).where(Suggestion.kind == KIND, Suggestion.status != "open")
        )
        if isinstance(p, dict)
    }
    new = 0
    for recipe_id, (title, said) in found.items():
        for name, why in said.items():
            thing = things.get(name)
            if thing is None or covers[name] & has.get(recipe_id, set()):
                continue
            if (str(recipe_id), str(thing.id)) in decided:
                continue
            target = {"recipe_id": str(recipe_id), "equipment_id": str(thing.id)}
            result = await session.execute(
                insert(Suggestion)
                .values(
                    kind=KIND,
                    target=target,
                    proposal={**target, "recipe_title": title, "equipment_name": thing.name},
                    reason=why,
                    model=MODEL,
                    prompt_version=VERSION,
                )
                .on_conflict_do_nothing(
                    index_elements=["kind", "target"], index_where=text("status = 'open'")
                )
                .returning(Suggestion.id)
            )
            new += result.scalar() is not None
    return new
