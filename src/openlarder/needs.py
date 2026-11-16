"""What a recipe needs: reading a need as typed, and writing a recipe's.
*Ray's equipment spec, 2026-11-15.*

A need is typed as an ingredient line is, in one box: "stand mixer or hand
mixer" is one need with two options, the source's first choice first, and
"9-inch springform pan" is a springform pan with a size. The size is kept
apart from the thing (recipe_equipment.detail) and is all of the source's
words that are kept: no method, no brand.

Each option is matched to the list by its key, as a line's is to an
ingredient. What any kitchen has is refused, since it is never recorded.
A name the list doesn't have makes a new thing, not in the list
(`listed` false, migration 0081): it is seen only with a recipe that
needs it, as an ingredient a recipe brings in is, so one typed into a
private collection stays there and one in a recipe waiting for review
waits with it. One that no recipe needs any more is removed.

Whether a recipe's needs are recorded at all is its equipment_checked:
saving with a need, or with "nothing special" said, sets it; saving with
neither leaves the recipe not recorded. Three states, never two
(models/equipment.py).
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.ingredients import match_key
from openlarder.models import (
    Equipment,
    EquipmentAlias,
    EquipmentCountsAs,
    EquipmentOption,
    Recipe,
    RecipeEquipment,
)

MAX_NEEDS = 30
MAX_NEED = 150
MAX_OPTIONS = 6

_NUMBER = r"(?:\d+(?:[.,/]\d+)?|[½⅓⅔¼¾⅛])"
_UNIT = (
    r"(?:inch(?:es)?|in\.?|\"|”|cm|mm|quarts?|qts?\.?|lit(?:er|re)s?|l|cups?|gallons?|gal\.?"
    r"|ounces?|oz\.?|pounds?|lbs?\.?)"
)
# A size or a capacity: "9-inch", "9 x 13 inch", "10- to 12-inch", "6-quart",
# "23cm", "1½-quart".
_SIZE = rf"{_NUMBER}{_NUMBER}?(?:\s*(?:x|×|by|-\s*to|to|–)\s*{_NUMBER})*\s*-?\s*{_UNIT}(?![a-z])"
_LEADING = re.compile(rf"^({_SIZE})[\s,]+(.+)$", re.IGNORECASE)
_TRAILING = re.compile(rf"^(.+?)[\s,]*\(?({_SIZE})\)?$", re.IGNORECASE)
_ONLY = re.compile(rf"^\(?{_SIZE}\)?$", re.IGNORECASE)
_OR = re.compile(r"\s+or\s+", re.IGNORECASE)
_ARTICLE = re.compile(r"^(?:an?|the)\s+", re.IGNORECASE)


class Refused(ValueError):
    """Why a need can't be saved, in words to show beside it."""


@dataclass
class Need:
    # The size, where one was given ("9-inch").
    detail: str | None
    # What meets it, as typed, first choice first.
    names: list[str]


def _sized(text: str) -> tuple[str | None, str]:
    """A size taken off the front or the end of a name: ("9-inch",
    "springform pan") from "9-inch springform pan" or "springform pan,
    9-inch"; (None, the name) when there's none."""
    if found := _LEADING.match(text):
        return " ".join(found.group(1).split()), found.group(2)
    if found := _TRAILING.match(text):
        return " ".join(found.group(2).split()), found.group(1)
    return None, text


def read(text: str) -> Need | None:
    """A need as typed; None for an empty box."""
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > MAX_NEED:
        raise Refused(f"A need is at most {MAX_NEED} characters: the thing, and its size.")
    detail: str | None = None
    names: list[str] = []
    for part in _OR.split(text):
        if _ONLY.match(part):
            raise Refused(
                f"“{part}” is a size. Name what it's the size of, like “9-inch cake pan”."
            )
        # "a 9-inch pan": the article first, or it hides the size.
        size, name = _sized(_ARTICLE.sub("", part))
        name = _ARTICLE.sub("", name).strip(" ,;.")
        if not match_key(name):
            raise Refused(f"“{part}” doesn't name anything.")
        # The first size given is the need's.
        detail = detail or size
        if match_key(name) not in {match_key(n) for n in names}:
            names.append(name)
    if len(names) > MAX_OPTIONS:
        raise Refused(f"A need offers at most {MAX_OPTIONS} things; “{text}” offers more.")
    return Need(detail=detail, names=names)


async def held_by(session: AsyncSession, key: str) -> tuple[Equipment, bool] | None:
    """The thing a key is the name of, or an unmarked other name of, and
    whether it was by another name."""
    by_name = await session.scalar(select(Equipment).where(Equipment.match_key == key))
    if by_name is not None:
        return by_name, False
    by_alias = await session.scalar(
        select(Equipment)
        .join(EquipmentAlias, EquipmentAlias.equipment_id == Equipment.id)
        .where(EquipmentAlias.match_key == key, EquipmentAlias.region.is_(None))
    )
    return (by_alias, True) if by_alias is not None else None


def assumed_message(thing: Equipment) -> str:
    """Said wherever something any kitchen has is typed for a recipe. The
    spec's words began "A {name}", which "Oven mitts" and "An oven" don't
    take; the name is quoted instead."""
    return f"“{thing.name}” is expected in any kitchen, so it isn't recorded."


def _as_named(name: str) -> str:
    """A new thing's name, as the list writes them: its first letter a
    capital, the rest as typed."""
    return name[:1].upper() + name[1:]


async def _thing(session: AsyncSession, name: str) -> Equipment:
    """The thing a typed name means: the list's, or a new one that isn't
    in the list."""
    key = match_key(name)
    if found := await held_by(session, key):
        thing, _ = found
        if thing.assumed:
            raise Refused(assumed_message(thing))
        return thing
    thing = Equipment(name=_as_named(name), match_key=key, listed=False)
    session.add(thing)
    await session.flush()
    return thing


async def of_recipes(
    session: AsyncSession, recipe_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[uuid.UUID, str | None, list[Equipment]]]]:
    """Each recipe's needs in order, as (the need's id, its size, what
    meets it by rank)."""
    out: dict[uuid.UUID, list[tuple[uuid.UUID, str | None, list[Equipment]]]] = {}
    if not recipe_ids:
        return out
    needs: dict[uuid.UUID, tuple[uuid.UUID, str | None, list[Equipment]]] = {}
    for need_id, recipe_id, detail in await session.execute(
        select(RecipeEquipment.id, RecipeEquipment.recipe_id, RecipeEquipment.detail)
        .where(RecipeEquipment.recipe_id.in_(recipe_ids))
        .order_by(RecipeEquipment.recipe_id, RecipeEquipment.position)
    ):
        needs[need_id] = (need_id, detail, [])
        out.setdefault(recipe_id, []).append(needs[need_id])
    for need_id, thing in await session.execute(
        select(EquipmentOption.recipe_equipment_id, Equipment)
        .join(Equipment, Equipment.id == EquipmentOption.equipment_id)
        .where(EquipmentOption.recipe_id.in_(recipe_ids))
        .order_by(EquipmentOption.recipe_equipment_id, EquipmentOption.rank)
    ):
        needs[need_id][2].append(thing)
    return out


def as_typed(detail: str | None, things: list[Equipment]) -> str:
    """A need as its box takes it back: "9-inch Springform pan or Round
    cake pan"."""
    named = " or ".join(t.name for t in things)
    return f"{detail} {named}" if detail else named


async def write(
    session: AsyncSession,
    recipe: Recipe,
    typed: list[str] | None,
    nothing_special: bool | None,
) -> None:
    """Make a recipe's needs what was typed. With neither given, nothing
    of them changes: a save that doesn't speak of equipment leaves it be."""
    if typed is None and nothing_special is None:
        return
    read_needs = [need for text in typed or [] if (need := read(text)) is not None]
    if len(read_needs) > MAX_NEEDS:
        raise Refused(f"A recipe can list at most {MAX_NEEDS} needs.")
    if read_needs and nothing_special:
        raise Refused(
            "“Nothing special” is checked and equipment is listed. Uncheck it, or take the"
            " equipment out."
        )
    wanted: list[tuple[str | None, list[Equipment]]] = []
    seen: set[tuple[uuid.UUID, ...]] = set()
    for need in read_needs:
        things: list[Equipment] = []
        for name in need.names:
            thing = await _thing(session, name)
            if thing.id not in {t.id for t in things}:
                things.append(thing)
        # Each need once, however it was typed twice.
        met_by = tuple(t.id for t in things)
        if met_by not in seen:
            seen.add(met_by)
            wanted.append((need.detail, things))

    now = (await of_recipes(session, [recipe.id])).get(recipe.id, [])
    same = [(d, [t.id for t in ts]) for _, d, ts in now] == [
        (d, [t.id for t in ts]) for d, ts in wanted
    ]
    if not same:
        # Rewritten, as the ingredient lines are; untouched when nothing of
        # them changed, so the history has a save's changes and no more.
        await session.execute(delete(RecipeEquipment).where(RecipeEquipment.recipe_id == recipe.id))
        await session.flush()
        for position, (detail, things) in enumerate(wanted, start=1):
            need_row = RecipeEquipment(recipe_id=recipe.id, position=position, detail=detail)
            session.add(need_row)
            await session.flush()
            for rank, thing in enumerate(things, start=1):
                session.add(
                    EquipmentOption(
                        recipe_equipment_id=need_row.id,
                        recipe_id=recipe.id,
                        rank=rank,
                        equipment_id=thing.id,
                    )
                )
    recipe.equipment_checked = bool(wanted) or bool(nothing_special)
    await session.flush()
    await sweep(session)


async def sweep(session: AsyncSession) -> None:
    """Remove what recipes brought in and no recipe needs any more: a
    thing that isn't in the list is there for its recipes alone."""
    await session.execute(
        delete(Equipment).where(
            Equipment.listed.is_(False),
            ~exists().where(EquipmentOption.equipment_id == Equipment.id),
            ~exists().where(EquipmentCountsAs.counts_as_id == Equipment.id),
        )
    )
