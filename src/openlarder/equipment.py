"""Equipment: what counts as what, and fixing the list (models/equipment.py,
migrations 0079 and 0080).

A thing can count as several others: a multicooker as a pressure cooker and
as a slow cooker (*Ray, 2026-11-15*). So what an ingredient does with a
parent column, this does with equipment_counts_as. A recipe that needs a
stand mixer is one that needs a mixer, so a thing's recipes are its own and
those of everything that counts as it: its family.

The list is the moderators' to change (*Ray's spec, 2026-11-15*: add,
rename, merge into, count as, also called, mark as any kitchen's, delete
when unused), as the ingredient list is. A name is matched by its key, made
as an ingredient's is, and a key means one thing: a thing's own, or an
unmarked other name's.
"""

import uuid

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from openlarder.ingredients import match_key
from openlarder.models import (
    Equipment,
    EquipmentAlias,
    EquipmentCountsAs,
    EquipmentOption,
    MergedRecord,
)


def family(*equipment_ids: uuid.UUID, name: str = "equipment_family"):
    """The things and everything that counts as them, as a select of IDs:
    asked for a mixer, the stand mixer and the hand mixer too. UNION, not
    UNION ALL, so a loop in what counts as what still ends; nothing the
    site does makes one, but rows written another way could."""
    tree = (
        select(Equipment.id).where(Equipment.id.in_(equipment_ids)).cte(name=name, recursive=True)
    )
    tree = tree.union(
        select(EquipmentCountsAs.equipment_id).where(EquipmentCountsAs.counts_as_id == tree.c.id)
    )
    return select(tree.c.id)


# Fixing the list.


class Taken(Exception):
    """The name is another thing's, or another name for one: merge."""

    def __init__(self, thing: Equipment) -> None:
        super().__init__(thing.name)
        self.thing = thing


class InUse(Exception):
    """Something still points at the thing: why, in words to show."""


async def _holder(session: AsyncSession, key: str) -> Equipment | None:
    """The thing a key is the name or an unmarked other name of."""
    return await session.scalar(
        select(Equipment).where(
            (Equipment.match_key == key)
            | Equipment.id.in_(
                select(EquipmentAlias.equipment_id).where(
                    EquipmentAlias.match_key == key, EquipmentAlias.region.is_(None)
                )
            )
        )
    )


def _named(name: str) -> tuple[str, str]:
    """A name with its spaces tidied, and its key."""
    name = " ".join(name.split())
    key = match_key(name)
    if not key:
        raise ValueError("A name needs at least one letter or number.")
    return name, key


async def _needing(session: AsyncSession, equipment_id: uuid.UUID) -> int:
    """How many recipes list the thing, whoever can see them: what stands
    in the way of a change is there whether or not the asker sees it."""
    found = await session.scalar(
        select(func.count(func.distinct(EquipmentOption.recipe_id))).where(
            EquipmentOption.equipment_id == equipment_id
        )
    )
    return found or 0


def _recipes(count: int) -> str:
    return "1 recipe lists" if count == 1 else f"{count:,} recipes list"


async def create(session: AsyncSession, name: str, assumed: bool = False) -> Equipment:
    """Add a thing to the list."""
    name, key = _named(name)
    if holder := await _holder(session, key):
        if holder.listed or holder.match_key != key:
            raise Taken(holder)
        # A recipe's form brought it in (needs.py): it is the list's now,
        # under the name the moderator gave it.
        # (Not as any kitchen's while a recipe lists it: set_assumed says so.)
        await set_assumed(session, holder, assumed)
        holder.name, holder.listed = name, True
        await session.flush()
        return holder
    thing = Equipment(name=name, match_key=key, assumed=assumed)
    session.add(thing)
    await session.flush()
    return thing


async def rename(session: AsyncSession, thing: Equipment, name: str) -> None:
    """Rename a thing. If that changes its key, the old name stays as
    another name for it, so a recipe written that way still finds it."""
    name, key = _named(name)
    if key != thing.match_key:
        holder = await _holder(session, key)
        if holder is not None and holder.id != thing.id:
            raise Taken(holder)
        # Its own other name, if it was one, is its name now.
        await session.execute(
            delete(EquipmentAlias).where(
                EquipmentAlias.match_key == key, EquipmentAlias.region.is_(None)
            )
        )
        session.add(
            EquipmentAlias(equipment_id=thing.id, name=thing.name, match_key=thing.match_key)
        )
        thing.match_key = key
    thing.name = name
    await session.flush()


async def add_alias(session: AsyncSession, thing: Equipment, name: str) -> EquipmentAlias:
    """Another name for a thing ("Stick blender"), which a typed name then
    finds it by."""
    name, key = _named(name)
    holder = await _holder(session, key)
    if holder is not None and holder.id != thing.id:
        raise Taken(holder)
    if holder is not None:
        raise ValueError(f"“{name}” already finds “{thing.name}”.")
    alias = EquipmentAlias(equipment_id=thing.id, name=name, match_key=key)
    session.add(alias)
    await session.flush()
    return alias


async def count_as(session: AsyncSession, thing: Equipment, broader: Equipment) -> None:
    """Make a thing count as another (a stand mixer as a mixer), beside
    whatever it counts as already. Refused if that would make a loop."""
    if broader.id == thing.id:
        raise ValueError("A thing can't count as itself.")
    below = set(await session.scalars(family(thing.id)))
    if broader.id in below:
        raise ValueError(
            f"“{broader.name}” already counts as “{thing.name}”, "
            "so it can't be the other way round too."
        )
    already = await session.get(EquipmentCountsAs, (thing.id, broader.id))
    if already is None:
        session.add(EquipmentCountsAs(equipment_id=thing.id, counts_as_id=broader.id))
        await session.flush()


async def stop_counting_as(session: AsyncSession, thing: Equipment, broader: Equipment) -> None:
    await session.execute(
        delete(EquipmentCountsAs).where(
            EquipmentCountsAs.equipment_id == thing.id,
            EquipmentCountsAs.counts_as_id == broader.id,
        )
    )


async def set_assumed(session: AsyncSession, thing: Equipment, assumed: bool) -> None:
    """Say a thing is expected in any kitchen, or that it isn't. Nothing
    assumed is on a recipe, so one a recipe lists can't become so."""
    if assumed and not thing.assumed and (count := await _needing(session, thing.id)):
        raise InUse(
            f"{_recipes(count)} “{thing.name}”. What any kitchen has is never on a recipe:"
            " take it off them first, or merge it into another."
        )
    thing.assumed = assumed
    await session.flush()


async def merge(session: AsyncSession, source: Equipment, target: Equipment) -> None:
    """Fold one thing into another: every recipe that needed it needs the
    other, and its name and other names become the other's."""
    if source.id == target.id:
        raise ValueError("A thing can't be merged into itself.")
    s, t = source.id, target.id
    if target.assumed and (count := await _needing(session, s)):
        raise InUse(
            f"{_recipes(count)} “{source.name}”, and “{target.name}” is expected in any"
            " kitchen, so no recipe can list it."
        )
    # A need that offered both offers the one kept, once: the option naming
    # the one going is dropped, and the rest keep their ranks.
    twin = aliased(EquipmentOption)
    await session.execute(
        delete(EquipmentOption).where(
            EquipmentOption.equipment_id == s,
            exists().where(
                twin.recipe_equipment_id == EquipmentOption.recipe_equipment_id,
                twin.equipment_id == t,
            ),
        )
    )
    await session.execute(
        update(EquipmentOption).where(EquipmentOption.equipment_id == s).values(equipment_id=t)
    )
    # Other names can't clash: a key means one thing.
    await session.execute(
        update(EquipmentAlias).where(EquipmentAlias.equipment_id == s).values(equipment_id=t)
    )
    # What the one going counted as, and what counted as it, do so of the
    # one kept; a link between the two, or one the other has, is dropped.
    link, kept = EquipmentCountsAs, aliased(EquipmentCountsAs)
    await session.execute(
        delete(link).where(
            link.equipment_id == s,
            (link.counts_as_id == t)
            | exists().where(kept.equipment_id == t, kept.counts_as_id == link.counts_as_id),
        )
    )
    await session.execute(update(link).where(link.equipment_id == s).values(equipment_id=t))
    await session.execute(
        delete(link).where(
            link.counts_as_id == s,
            (link.equipment_id == t)
            | exists().where(kept.counts_as_id == t, kept.equipment_id == link.equipment_id),
        )
    )
    await session.execute(update(link).where(link.counts_as_id == s).values(counts_as_id=t))
    # The one kept can't now count as something that counts as it (A into
    # B, where B counted as C and C as A): such a link goes.
    below = set(await session.scalars(family(t))) - {t}
    if below:
        await session.execute(
            delete(link).where(link.equipment_id == t, link.counts_as_id.in_(below))
        )
    session.add(EquipmentAlias(equipment_id=t, name=source.name, match_key=source.match_key))
    if target.shopping_term is None:
        target.shopping_term = source.shopping_term
    if target.wikidata_id is None:
        target.wikidata_id = source.wikidata_id
    # Where it went, for its old address to say (pages.py).
    session.add(MergedRecord(kind="equipment", gone_id=s, kept_id=t))
    await session.delete(source)
    await session.flush()


async def remove(session: AsyncSession, thing: Equipment) -> None:
    """Delete a thing no recipe lists and nothing counts as; its other
    names, and what it counted as, go with it."""
    if count := await _needing(session, thing.id):
        raise InUse(f"{_recipes(count)} “{thing.name}”. Merge it into another instead.")
    counted = await session.scalar(
        select(exists().where(EquipmentCountsAs.counts_as_id == thing.id))
    )
    if counted:
        raise InUse(
            f"Something counts as “{thing.name}”. Stop that first, or merge it into another."
        )
    await session.delete(thing)
    await session.flush()
