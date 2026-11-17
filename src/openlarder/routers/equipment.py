"""Equipment: the list, and one thing's page.

Reading is public, like the rest of the catalog. The list is what a recipe
can be recorded as needing, the most needed first; what any kitchen has
(`assumed`) is left out unless asked for, since no recipe lists it. It can
be narrowed by name, or by another name, as someone types.

A thing's page lists the recipes that need it, or anything that counts as
it, each with how the need reads there. Every count is of the recipes the
viewer can see. A thing a recipe's form brought in is seen with a recipe
that needs it (visibility.equipment_seen_by).

A need is checked as an ingredient line is (POST /api/equipment/check
for the recipe form's boxes, /check-cell for a row of a whole book), to
say what it will be matched to, or that nothing matches and what is named
like it, before saving does it (*Ray, 2026-11-16: equipment is treated as
ingredients are*).

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

from openlarder import equipment, needs, shops, visibility
from openlarder.auth import CurrentUser, ModeratorUser, SameOrigin, Viewer
from openlarder.db import Session
from openlarder.models import (
    Equipment,
    EquipmentAlias,
    EquipmentCountsAs,
    EquipmentOption,
    Recipe,
)
from openlarder.routers.ingredients import UsedBy, contains_pattern, recipes_where

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
    # A page of the recipes that need it, each with how the need reads
    # (line): those needing exactly this, or with under, anything that
    # counts as it too. And how many that list holds in all.
    recipes: list[UsedBy] = []
    listed_total: int = 0
    # Recipes recorded as needing exactly this.
    total: int
    # Recipes needing it or anything that counts as it.
    family_total: int
    # What a Shop link searches a kitchen shop for, when it isn't the name.
    shopping_term: str | None = None


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
    # Count the recipes needing anything that counts as each one too, and
    # order by that: what a search finds when it's chosen (a mixer finds
    # the stand mixer's). As the ingredients' list does.
    under: bool = False,
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
    if under:
        tree = equipment.rooted_family(*listed, name="under_each")
        uses = (
            select(
                tree.c.root.label("equipment_id"),
                func.count(func.distinct(EquipmentOption.recipe_id)).label("n"),
            )
            .join(EquipmentOption, EquipmentOption.equipment_id == tree.c.id)
            .where(visibility.needs_seen_by(viewer))
            .group_by(tree.c.root)
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
        return await get_equipment(equipment_id, session, None, offset=0, under=True)
    except HTTPException as refused:
        if refused.status_code != status.HTTP_404_NOT_FOUND:
            raise
        return None


@router.get("/{equipment_id}", response_model=EquipmentOut)
async def get_equipment(
    equipment_id: uuid.UUID,
    session: Session,
    viewer: Viewer,
    offset: int = Query(0, ge=0),
    # List the recipes needing anything that counts as it too.
    under: bool = False,
) -> EquipmentOut:
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
    named = (
        EquipmentOption.equipment_id.in_(equipment.family(equipment_id))
        if under
        else EquipmentOption.equipment_id == equipment_id
    )
    recipes, listed_total = await recipes_where(
        session,
        Recipe.id.in_(select(EquipmentOption.recipe_id).where(named)),
        visibility.recipes_seen_by(viewer),
        offset=offset,
    )
    # Each listed recipe's need of it, as it reads: the first, if several.
    met = set(
        await session.scalars(
            select(EquipmentOption.recipe_equipment_id).where(
                EquipmentOption.recipe_id.in_([r.id for r in recipes]), named
            )
        )
    )
    reads = await needs.of_recipes(session, [r.id for r in recipes])
    for r in recipes:
        r.line = next(
            (
                needs.as_typed(detail, things)
                for need_id, detail, things in reads.get(r.id, [])
                if need_id in met
            ),
            None,
        )
    return EquipmentOut(
        id=thing.id,
        name=thing.name,
        assumed=thing.assumed,
        recipes=recipes,
        listed_total=listed_total,
        aliases=[AliasOut(id=a, name=n) for a, n in aliases],
        counts_as=[Related(id=i, name=n) for i, n in counts_as],
        includes=includes,
        total=total or 0,
        family_total=family_total or 0,
        shopping_term=thing.shopping_term,
    )


# Checking needs as they're typed


# Far more than a recipe may list (needs.MAX_NEEDS), and an end to it.
MAX_CHECKED = 100


class NeedsIn(BaseModel):
    needs: list[str] = Field(max_length=MAX_CHECKED)


class OptionRead(BaseModel):
    # As typed, without its size.
    name: str
    # What it will be matched to; none for a name the list doesn't have,
    # which saving makes a new thing of.
    equipment: Related | None = None
    # Matched by another name for it.
    alias: bool = False
    # When there isn't: things named like it, as an unmatched ingredient
    # line is given ingredients named like it.
    similar: list[Related] = []


class NeedRead(BaseModel):
    detail: str | None = None
    options: list[OptionRead] = []
    # Why saving would refuse it: something any kitchen has, a size alone.
    problem: str | None = None


# Looking for names like each unmatched option is a query apiece, as it is
# for ingredient lines (routers/recipes.py).
MAX_SIMILAR = 30


async def _read(session: Session, user, typed: list[str]) -> list[NeedRead]:
    """Each need read as saving would read it. A thing the asker can't see
    (one only a recipe hidden from them needs) is answered as new, and is
    never among the names like another: that it exists isn't theirs to
    learn."""
    seen_by = visibility.equipment_seen_by(user)
    seen = set(await session.scalars(select(Equipment.id).where(seen_by)))
    looked = 0
    out = []
    for text in typed:
        try:
            need = needs.read(text)
        except needs.Refused as refused:
            out.append(NeedRead(problem=str(refused)))
            continue
        if need is None:
            out.append(NeedRead())
            continue
        read = NeedRead(detail=need.detail)
        for name in need.names:
            found = await needs.held_by(session, equipment.match_key(name))
            option = OptionRead(name=name)
            if found and found[0].id in seen:
                thing, option.alias = found
                option.equipment = Related(id=thing.id, name=thing.name)
                if thing.assumed:
                    read.problem = needs.assumed_message(thing)
            elif looked < MAX_SIMILAR:
                looked += 1
                option.similar = [
                    Related(id=i, name=n) for i, n in await needs.like(session, name, seen_by)
                ]
            read.options.append(option)
        out.append(read)
    return out


@router.post("/check", response_model=list[NeedRead], dependencies=[SameOrigin])
async def check_needs(body: NeedsIn, user: CurrentUser, session: Session) -> list[NeedRead]:
    """The recipe form's needs, a box apiece, as saving would read them."""
    return await _read(session, user, body.needs)


class CellIn(BaseModel):
    cell: str = Field(max_length=2000)


class CellNeed(NeedRead):
    # The need as typed, to say which one a check is about.
    text: str


class CellRead(BaseModel):
    # "none" alone: the recipe needs nothing special.
    nothing_special: bool = False
    needs: list[CellNeed] = []


@router.post("/check-cell", response_model=CellRead, dependencies=[SameOrigin])
async def check_cell(body: CellIn, user: CurrentUser, session: Session) -> CellRead:
    """A row's needs typed into one cell (entering a whole book), parted as
    saving parts them and each read as saving would read it, so the row can
    say what each matched as it says of its ingredients."""
    parts = needs.cell_parts(body.cell)[:MAX_CHECKED]
    if len(parts) == 1 and needs.says_none(parts[0]):
        return CellRead(nothing_special=True)
    reads = iter(await _read(session, user, [p for p in parts if not needs.says_none(p)]))
    return CellRead(
        needs=[
            CellNeed(text=part, problem=needs.none_beside(part))
            if needs.says_none(part)
            else CellNeed(text=part, **next(reads).model_dump())
            for part in parts
        ]
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


async def _thing_or_404(session: Session, equipment_id: uuid.UUID, viewer) -> Equipment:
    """The thing, if the moderator can see it: one a private recipe brought
    in isn't theirs to change either."""
    thing = await session.scalar(
        select(Equipment).where(Equipment.id == equipment_id, visibility.equipment_seen_by(viewer))
    )
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
    thing = await _thing_or_404(session, equipment_id, moderator)
    try:
        await equipment.rename(session, thing, body.name)
    except CHANGE_REFUSED as exc:
        raise _refused(exc) from None
    await session.commit()
    return Named(id=thing.id, name=thing.name)


class TermIn(BaseModel):
    # Nothing, or the name again: search for the name.
    term: str | None = Field(None, max_length=shops.MAX_TERM)


@router.put("/{equipment_id}/shopping-term", response_model=Named, dependencies=[SameOrigin])
async def set_shopping_term(
    equipment_id: uuid.UUID, body: TermIn, moderator: ModeratorUser, session: Session
) -> Named:
    """What a Shop link searches a kitchen shop for, when the name isn't
    what's sold ("Dutch oven": "enameled dutch oven, 5 qt"); answers with
    the thing. As an ingredient's is set (routers/ingredients.py)."""
    thing = await _thing_or_404(session, equipment_id, moderator)
    thing.shopping_term = shops.shopping_term(body.term, thing.name)
    await session.commit()
    return Named(id=thing.id, name=thing.name)


@router.put("/{equipment_id}/assumed", response_model=Named, dependencies=[SameOrigin])
async def set_assumed(
    equipment_id: uuid.UUID, body: AssumedIn, moderator: ModeratorUser, session: Session
) -> Named:
    """Say whether any kitchen has it. One a recipe lists can't become so."""
    thing = await _thing_or_404(session, equipment_id, moderator)
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
    source = await _thing_or_404(session, equipment_id, moderator)
    target = await _thing_or_404(session, body.into, moderator)
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
    thing = await _thing_or_404(session, equipment_id, moderator)
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
    thing = await _thing_or_404(session, equipment_id, moderator)
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
    await _thing_or_404(session, equipment_id, moderator)
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
    thing = await _thing_or_404(session, equipment_id, moderator)
    broader = await _thing_or_404(session, broader_id, moderator)
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
    thing = await _thing_or_404(session, equipment_id, moderator)
    broader = await _thing_or_404(session, broader_id, moderator)
    await equipment.stop_counting_as(session, thing, broader)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
