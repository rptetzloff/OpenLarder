"""Equipment: the list, and one thing's page.

Reading is public, like the rest of the catalog. The list is what a recipe
can be recorded as needing, the most needed first; what any kitchen has
(`assumed`) is left out unless asked for, since no recipe lists it. It can
be narrowed by name, or by another name, as someone types.

A recipe's needs can't be recorded yet (the recipe form's field comes
next), so every count here is of none. They are counted all the same, of
the recipes the viewer can see, so the list is right the day they can.

Changing the list is for moderators, as changing the ingredient list is
(*Ray's spec, 2026-11-15*): adding a thing, renaming it, merging it into
another, what it counts as, its other names, whether any kitchen has it,
and deleting one nothing uses. Each change is in the edit history
(migration 0080) and can be undone from the thing's page.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, exists, func, select

from openlarder import equipment, visibility
from openlarder.auth import ModeratorUser, SameOrigin, Viewer
from openlarder.db import Session
from openlarder.models import Equipment, EquipmentAlias, EquipmentCountsAs, EquipmentOption
from openlarder.routers.ingredients import contains_pattern

router = APIRouter(prefix="/api/equipment", tags=["equipment"])

# The whole list on one page while it's a couple of hundred things: 140 at
# the start (migration 0079), where ingredients, in their thousands, come
# 100 at a time.
PAGE = 200


class Related(BaseModel):
    id: uuid.UUID
    name: str


class EquipmentSummary(BaseModel):
    id: uuid.UUID
    name: str
    # Expected in any kitchen, so no recipe lists it.
    assumed: bool
    # Recipes recorded as needing exactly this.
    recipes: int
    # What it counts as (a multicooker: a pressure cooker, a slow cooker)
    # and its other names, for the list's line beneath its name.
    counts_as: list[Related] = []
    aliases: list[str] = []


class EquipmentList(BaseModel):
    equipment: list[EquipmentSummary]
    total: int


class AliasOut(BaseModel):
    id: uuid.UUID
    name: str


class EquipmentOut(BaseModel):
    id: uuid.UUID
    name: str
    assumed: bool
    aliases: list[AliasOut]
    # Broader and narrower: a stand mixer counts as a mixer, and a mixer
    # includes a stand mixer. A thing can count as more than one.
    counts_as: list[Related]
    includes: list[Related]
    # Recipes recorded as needing exactly this.
    total: int
    # Recipes needing it or anything that counts as it.
    family_total: int


def _needing(*conditions: ColumnElement[bool], viewer):
    """How many recipes the viewer can see need a thing, among the options
    meeting the conditions."""
    return select(func.count(func.distinct(EquipmentOption.recipe_id))).where(
        *conditions, visibility.needs_seen_by(viewer)
    )


@router.get("", response_model=EquipmentList)
async def list_equipment(
    session: Session,
    viewer: Viewer,
    q: str = "",
    offset: int = Query(0, ge=0),
    # "uses": the most needed first; "name": A to Z.
    sort: Literal["uses", "name"] = "uses",
    # What any kitchen has, too. Without it, only what a recipe can list.
    assumed: bool = False,
) -> EquipmentList:
    listed: list[ColumnElement[bool]] = [visibility.equipment_seen_by(viewer)]
    if not assumed:
        listed.append(Equipment.assumed.is_(False))
    if q.strip():
        like = contains_pattern(" ".join(q.split()))
        listed.append(
            Equipment.name.ilike(like, escape="\\")
            | exists().where(
                EquipmentAlias.equipment_id == Equipment.id,
                EquipmentAlias.name.ilike(like, escape="\\"),
            )
        )
    uses = (
        select(
            EquipmentOption.equipment_id,
            func.count(func.distinct(EquipmentOption.recipe_id)).label("n"),
        )
        .where(visibility.needs_seen_by(viewer))
        .group_by(EquipmentOption.equipment_id)
        .subquery()
    )
    query = (
        select(Equipment.id, Equipment.name, Equipment.assumed, func.coalesce(uses.c.n, 0))
        .outerjoin(uses, uses.c.equipment_id == Equipment.id)
        .where(*listed)
    )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    order = (
        (func.lower(Equipment.name), Equipment.id)
        if sort == "name"
        else (func.coalesce(uses.c.n, 0).desc(), func.lower(Equipment.name), Equipment.id)
    )
    rows = (await session.execute(query.order_by(*order).offset(offset).limit(PAGE))).all()
    ids = [r[0] for r in rows]
    counts_as: dict[uuid.UUID, list[Related]] = {}
    for i, broader, name in await session.execute(
        select(EquipmentCountsAs.equipment_id, Equipment.id, Equipment.name)
        .join(Equipment, Equipment.id == EquipmentCountsAs.counts_as_id)
        .where(EquipmentCountsAs.equipment_id.in_(ids), visibility.equipment_seen_by(viewer))
        .order_by(func.lower(Equipment.name))
    ):
        counts_as.setdefault(i, []).append(Related(id=broader, name=name))
    aliases: dict[uuid.UUID, list[str]] = {}
    for i, name, region in await session.execute(
        select(EquipmentAlias.equipment_id, EquipmentAlias.name, EquipmentAlias.region)
        .where(EquipmentAlias.equipment_id.in_(ids))
        .order_by(func.lower(EquipmentAlias.name))
    ):
        aliases.setdefault(i, []).append(f"{name} ({region})" if region else name)
    return EquipmentList(
        equipment=[
            EquipmentSummary(
                id=i,
                name=n,
                assumed=a,
                recipes=c,
                counts_as=counts_as.get(i, []),
                aliases=aliases.get(i, []),
            )
            for i, n, a, c in rows
        ],
        total=total or 0,
    )


async def as_signed_out(session, equipment_id: uuid.UUID) -> EquipmentOut | None:
    """The thing as someone signed out gets it from the route below, or
    None when they don't: what the server may write into a page before the
    browser does (pages.py)."""
    try:
        return await get_equipment(equipment_id, session, None)
    except HTTPException as refused:
        if refused.status_code != status.HTTP_404_NOT_FOUND:
            raise
        return None


@router.get("/{equipment_id}", response_model=EquipmentOut)
async def get_equipment(equipment_id: uuid.UUID, session: Session, viewer: Viewer) -> EquipmentOut:
    thing = await session.scalar(
        select(Equipment).where(Equipment.id == equipment_id, visibility.equipment_seen_by(viewer))
    )
    if thing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such equipment.")
    aliases = await session.execute(
        select(EquipmentAlias.id, EquipmentAlias.name)
        .where(EquipmentAlias.equipment_id == equipment_id)
        .order_by(func.lower(EquipmentAlias.name))
    )
    counts_as = await session.execute(
        select(Equipment.id, Equipment.name)
        .join(EquipmentCountsAs, EquipmentCountsAs.counts_as_id == Equipment.id)
        .where(EquipmentCountsAs.equipment_id == equipment_id, visibility.equipment_seen_by(viewer))
        .order_by(func.lower(Equipment.name))
    )
    includes = [
        Related(id=i, name=n)
        for i, n in await session.execute(
            select(Equipment.id, Equipment.name)
            .join(EquipmentCountsAs, EquipmentCountsAs.equipment_id == Equipment.id)
            .where(
                EquipmentCountsAs.counts_as_id == equipment_id,
                visibility.equipment_seen_by(viewer),
            )
            .order_by(func.lower(Equipment.name))
        )
    ]
    total = await session.scalar(
        _needing(EquipmentOption.equipment_id == equipment_id, viewer=viewer)
    )
    family_total = total
    if includes:
        family_total = await session.scalar(
            _needing(
                EquipmentOption.equipment_id.in_(equipment.family(equipment_id)), viewer=viewer
            )
        )
    return EquipmentOut(
        id=thing.id,
        name=thing.name,
        assumed=thing.assumed,
        aliases=[AliasOut(id=a, name=n) for a, n in aliases],
        counts_as=[Related(id=i, name=n) for i, n in counts_as],
        includes=includes,
        total=total or 0,
        family_total=family_total or 0,
    )


# Fixing the list


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class NewEquipment(NameIn):
    # Expected in any kitchen, so never recorded on a recipe.
    assumed: bool = False


class AssumedIn(BaseModel):
    assumed: bool


class MergeInto(BaseModel):
    into: uuid.UUID


class Named(BaseModel):
    id: uuid.UUID
    name: str


async def _thing_or_404(session: Session, equipment_id: uuid.UUID) -> Equipment:
    thing = await session.get(Equipment, equipment_id)
    if thing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such equipment.")
    return thing


def _taken(exc: equipment.Taken) -> HTTPException:
    # The other thing, so the page can offer to merge into it.
    other = exc.thing
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "message": f"“{other.name}” is already in the list, or another name for it is.",
            "equipment": {"id": str(other.id), "name": other.name},
        },
    )


def _refused(exc: Exception) -> HTTPException:
    """What a change is refused for, in its own words: a name that is no
    name or a loop (422), a name taken (409, with whose), something still
    using the thing (409)."""
    if isinstance(exc, equipment.Taken):
        return _taken(exc)
    if isinstance(exc, equipment.InUse):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


CHANGE_REFUSED = (ValueError, equipment.Taken, equipment.InUse)


@router.post(
    "", response_model=Named, status_code=status.HTTP_201_CREATED, dependencies=[SameOrigin]
)
async def add_equipment(body: NewEquipment, moderator: ModeratorUser, session: Session) -> Named:
    """Add a thing to the list."""
    try:
        thing = await equipment.create(session, body.name, body.assumed)
    except CHANGE_REFUSED as exc:
        raise _refused(exc) from None
    await session.commit()
    return Named(id=thing.id, name=thing.name)


@router.patch("/{equipment_id}", response_model=Named, dependencies=[SameOrigin])
async def rename_equipment(
    equipment_id: uuid.UUID, body: NameIn, moderator: ModeratorUser, session: Session
) -> Named:
    thing = await _thing_or_404(session, equipment_id)
    try:
        await equipment.rename(session, thing, body.name)
    except CHANGE_REFUSED as exc:
        raise _refused(exc) from None
    await session.commit()
    return Named(id=thing.id, name=thing.name)


@router.put("/{equipment_id}/assumed", response_model=Named, dependencies=[SameOrigin])
async def set_assumed(
    equipment_id: uuid.UUID, body: AssumedIn, moderator: ModeratorUser, session: Session
) -> Named:
    """Say whether any kitchen has it. One a recipe lists can't become so."""
    thing = await _thing_or_404(session, equipment_id)
    try:
        await equipment.set_assumed(session, thing, body.assumed)
    except CHANGE_REFUSED as exc:
        raise _refused(exc) from None
    await session.commit()
    return Named(id=thing.id, name=thing.name)


@router.post("/{equipment_id}/merge", response_model=Named, dependencies=[SameOrigin])
async def merge_equipment(
    equipment_id: uuid.UUID, body: MergeInto, moderator: ModeratorUser, session: Session
) -> Named:
    """Merge this thing into another; answers with the one that's left."""
    source = await _thing_or_404(session, equipment_id)
    target = await _thing_or_404(session, body.into)
    try:
        await equipment.merge(session, source, target)
    except CHANGE_REFUSED as exc:
        raise _refused(exc) from None
    await session.commit()
    return Named(id=target.id, name=target.name)


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SameOrigin])
async def delete_equipment(
    equipment_id: uuid.UUID, moderator: ModeratorUser, session: Session
) -> Response:
    thing = await _thing_or_404(session, equipment_id)
    try:
        await equipment.remove(session, thing)
    except CHANGE_REFUSED as exc:
        raise _refused(exc) from None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{equipment_id}/aliases",
    response_model=AliasOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def add_alias(
    equipment_id: uuid.UUID, body: NameIn, moderator: ModeratorUser, session: Session
) -> AliasOut:
    """Another name for the thing, which a typed name then finds it by."""
    thing = await _thing_or_404(session, equipment_id)
    try:
        alias = await equipment.add_alias(session, thing, body.name)
    except CHANGE_REFUSED as exc:
        raise _refused(exc) from None
    await session.commit()
    return AliasOut(id=alias.id, name=alias.name)


@router.delete(
    "/{equipment_id}/aliases/{alias_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SameOrigin],
)
async def delete_alias(
    equipment_id: uuid.UUID, alias_id: uuid.UUID, moderator: ModeratorUser, session: Session
) -> Response:
    """Stop finding the thing by this name."""
    alias = await session.get(EquipmentAlias, alias_id)
    if alias is None or alias.equipment_id != equipment_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such name for this equipment.")
    await session.delete(alias)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{equipment_id}/counts-as/{broader_id}", response_model=Named, dependencies=[SameOrigin]
)
async def count_as(
    equipment_id: uuid.UUID, broader_id: uuid.UUID, moderator: ModeratorUser, session: Session
) -> Named:
    """Make this thing count as another, beside whatever it counts as
    already; answers with this thing."""
    thing = await _thing_or_404(session, equipment_id)
    broader = await _thing_or_404(session, broader_id)
    try:
        await equipment.count_as(session, thing, broader)
    except CHANGE_REFUSED as exc:
        raise _refused(exc) from None
    await session.commit()
    return Named(id=thing.id, name=thing.name)


@router.delete(
    "/{equipment_id}/counts-as/{broader_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SameOrigin],
)
async def stop_counting_as(
    equipment_id: uuid.UUID, broader_id: uuid.UUID, moderator: ModeratorUser, session: Session
) -> Response:
    thing = await _thing_or_404(session, equipment_id)
    broader = await _thing_or_404(session, broader_id)
    await equipment.stop_counting_as(session, thing, broader)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
