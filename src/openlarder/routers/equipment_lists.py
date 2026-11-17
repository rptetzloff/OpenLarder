"""Your equipment: lists of what you have and want (migration 0084).

*Ray's equipment spec, 2026-11-15*, had one checklist a person. *Ray,
2026-11-16:* "it should work like larder and book lists work", and of the
two, "Named lists, like the larder". So this is routers/larder.py over
again, for equipment, and what's said there holds here.

Lists are yours to name and order ("Kitchen", "Cabin"). An item is your own
name for something ("Nana's Dutch oven") and the piece of equipment it is,
matched by name when you add it (a thing's name or another name for it,
with a size typed beside it set aside), or chosen. A name that matches
nothing stays unmatched: it's kept, and doesn't count, but it never adds to
the equipment list, since yours is private and the catalog isn't. Each item
is one you have, or one you want (*Ray, 2026-11-16: "Have / Want"*, as a
book on a shelf is; a larder's "running low" has no meaning here): wanted
stays on the list, so you remember it, and doesn't count.

A list is its owner's, and shared with the household groups they choose, as
a larder's is: a group's view members see it, its edit and admin members
change what's on it. Renaming, removing and sharing a list stay with its
owner.

What someone has (`had`, `held`) is what's on their lists and those shared
with them, had and not wanted, matched, and theirs to see. Search keeps to
it (routers/search.py, equipment=mine), and a recipe's page says which of
its needs it doesn't meet (routers/recipes.py).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select

from openlarder import equipment as kit
from openlarder import needs, visibility
from openlarder.auth import CurrentUser, SameOrigin
from openlarder.db import Session
from openlarder.ingredients import match_key
from openlarder.models import (
    Equipment,
    EquipmentAlias,
    EquipmentList,
    EquipmentListGroup,
    EquipmentListItem,
    Group,
    GroupMember,
    User,
)

router = APIRouter(prefix="/api/equipment-lists", tags=["equipment lists"])
# The larder's limits.
MAX_LISTS = 50
MAX_ITEMS = 2000
State = Literal["have", "want"]
# Group roles that change what's on a list shared with them.
EDITING_ROLES = ("edit", "admin")


def seen_list_ids(user: User):
    """The lists a person sees: their own, and those shared with a group
    they're in."""
    shared = (
        select(EquipmentListGroup.list_id)
        .join(GroupMember, GroupMember.group_id == EquipmentListGroup.group_id)
        .where(GroupMember.user_id == user.id)
    )
    return select(EquipmentList.id).where(
        or_(EquipmentList.owner_id == user.id, EquipmentList.id.in_(shared))
    )


async def had(
    session,
    viewer: User,
    lists: list[uuid.UUID] = (),
    items: list[uuid.UUID] = (),
    without: list[uuid.UUID] = (),
) -> list[uuid.UUID]:
    """The equipment the viewer has, as larder_ingredients finds what's in
    their larder: on their lists and those shared with them, had and not
    wanted, of the equipment they may see; only the things named, if some
    are, or else only the lists named, if some are; less the things left
    out."""
    query = (
        select(func.distinct(EquipmentListItem.equipment_id))
        .join(EquipmentList, EquipmentList.id == EquipmentListItem.list_id)
        .join(Equipment, Equipment.id == EquipmentListItem.equipment_id)
        .where(
            EquipmentList.id.in_(seen_list_ids(viewer)),
            EquipmentListItem.state == "have",
            visibility.equipment_seen_by(viewer),
        )
    )
    if items:
        query = query.where(EquipmentListItem.id.in_(items))
    elif lists:
        query = query.where(EquipmentList.id.in_(lists))
    if without:
        query = query.where(EquipmentListItem.id.not_in(without))
    return list(await session.scalars(query))


async def held(session, viewer: User | None) -> set[uuid.UUID] | None:
    """Everything someone has, and everything each thing of theirs counts
    as, to hold a need against: with a stand mixer, a mixer too. None for
    someone signed out, or with nothing that counts on a list: there's
    nothing to say of what they don't have until they've said what they
    do."""
    if viewer is None:
        return None
    own = await had(session, viewer)
    if not own:
        return None
    return set(await session.scalars(kit.ancestry(*own, name="held_equipment")))


@dataclass
class Access:
    row: EquipmentList
    owner: bool
    editable: bool


async def _access(session, user: User, list_id: uuid.UUID) -> Access:
    """The list, and what this person may do with it; 404 if they can't see
    it."""
    row = await session.get(EquipmentList, list_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such list.")
    if row.owner_id == user.id:
        return Access(row, owner=True, editable=True)
    roles = set(
        await session.scalars(
            select(GroupMember.role)
            .join(EquipmentListGroup, EquipmentListGroup.group_id == GroupMember.group_id)
            .where(EquipmentListGroup.list_id == row.id, GroupMember.user_id == user.id)
        )
    )
    if not roles:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such list.")
    return Access(row, owner=False, editable=bool(roles & set(EDITING_ROLES)))


async def _editable(session, user: User, list_id: uuid.UUID) -> Access:
    access = await _access(session, user, list_id)
    if not access.editable:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can see this list, but not change what's on it."
        )
    return access


async def _owned(session, user: User, list_id: uuid.UUID) -> EquipmentList:
    access = await _access(session, user, list_id)
    if not access.owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the list's owner can do that.")
    return access.row


class ItemOut(BaseModel):
    id: uuid.UUID
    list_id: uuid.UUID
    name: str
    state: State
    equipment_id: uuid.UUID | None
    # The thing's name, when there's one you may see.
    equipment: str | None
    updated_at: datetime


class GroupRef(BaseModel):
    id: uuid.UUID
    name: str


class ListOut(BaseModel):
    id: uuid.UUID
    name: str
    position: int
    items: list[ItemOut]
    # Yours, or shared with you by its owner (their display name).
    mine: bool = True
    owner_name: str | None = None
    # Whether you may change what's on it.
    editable: bool = True
    # The groups it's shared with: all of them for its owner, the ones
    # you're in otherwise.
    shared_with: list[GroupRef] = []


class Lists(BaseModel):
    lists: list[ListOut]
    # Items that count as had: have, and matched.
    counted: int
    # Your groups, to share a list with.
    groups: list[GroupRef] = []


def _tidy(text: str) -> str:
    return " ".join(text.split())


async def _names(session, user: User, ids) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = await session.execute(
        select(Equipment.id, Equipment.name).where(
            Equipment.id.in_(ids), visibility.equipment_seen_by(user)
        )
    )
    return dict(rows.all())


def _item(item: EquipmentListItem, names: dict) -> ItemOut:
    return ItemOut(
        id=item.id,
        list_id=item.list_id,
        name=item.name,
        state=item.state,  # type: ignore[arg-type]
        equipment_id=item.equipment_id if item.equipment_id in names else None,
        equipment=names.get(item.equipment_id),
        updated_at=item.updated_at,
    )


@router.get("", response_model=Lists)
async def mine(user: CurrentUser, session: Session) -> Lists:
    """Your lists, then those shared with you."""
    lists = list(
        await session.scalars(
            select(EquipmentList)
            .where(EquipmentList.id.in_(seen_list_ids(user)))
            .order_by(
                (EquipmentList.owner_id != user.id),
                EquipmentList.position,
                EquipmentList.created_at,
            )
        )
    )
    ids = [lst.id for lst in lists]
    items = list(
        await session.scalars(
            select(EquipmentListItem)
            .where(EquipmentListItem.list_id.in_(ids))
            .order_by(func.lower(EquipmentListItem.name))
        )
    )
    names = await _names(session, user, [i.equipment_id for i in items])
    by_list: dict[uuid.UUID, list[ItemOut]] = {}
    for item in items:
        by_list.setdefault(item.list_id, []).append(_item(item, names))
    my_groups = dict(
        (
            await session.execute(
                select(Group.id, Group.name)
                .join(GroupMember, GroupMember.group_id == Group.id)
                .where(GroupMember.user_id == user.id)
                .order_by(func.lower(Group.name))
            )
        ).all()
    )
    sharing: dict[uuid.UUID, list[GroupRef]] = {}
    for list_id, group_id, name in await session.execute(
        select(EquipmentListGroup.list_id, Group.id, Group.name)
        .join(Group, Group.id == EquipmentListGroup.group_id)
        .where(EquipmentListGroup.list_id.in_(ids))
        .order_by(func.lower(Group.name))
    ):
        sharing.setdefault(list_id, []).append(GroupRef(id=group_id, name=name))
    owners = dict(
        (
            await session.execute(
                select(User.id, User.display_name).where(
                    User.id.in_({lst.owner_id for lst in lists if lst.owner_id != user.id})
                )
            )
        ).all()
    )
    out = []
    for lst in lists:
        own = lst.owner_id == user.id
        shared = sharing.get(lst.id, [])
        editable = own
        if not own:
            roles = set(
                await session.scalars(
                    select(GroupMember.role).where(
                        GroupMember.user_id == user.id,
                        GroupMember.group_id.in_([g.id for g in shared]),
                    )
                )
            )
            editable = bool(roles & set(EDITING_ROLES))
        out.append(
            ListOut(
                id=lst.id,
                name=lst.name,
                position=lst.position,
                items=by_list.get(lst.id, []),
                mine=own,
                owner_name=None if own else owners.get(lst.owner_id),
                editable=editable,
                shared_with=shared if own else [g for g in shared if g.id in my_groups],
            )
        )
    return Lists(
        lists=out,
        counted=sum(1 for i in items if i.state == "have" and i.equipment_id in names),
        groups=[GroupRef(id=i, name=n) for i, n in my_groups.items()],
    )


class ListIn(BaseModel):
    name: str = Field(max_length=100)
    position: int | None = None


def _one(all_lists: Lists, list_id: uuid.UUID) -> ListOut:
    return next(lst for lst in all_lists.lists if lst.id == list_id)


@router.post("/lists", response_model=ListOut, status_code=201, dependencies=[SameOrigin])
async def add_list(body: ListIn, user: CurrentUser, session: Session) -> ListOut:
    name = _tidy(body.name)
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the list a name.")
    count = await session.scalar(select(func.count()).where(EquipmentList.owner_id == user.id))
    if count >= MAX_LISTS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"At most {MAX_LISTS} lists.")
    row = EquipmentList(owner_id=user.id, name=name, position=body.position or count)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ListOut(id=row.id, name=row.name, position=row.position, items=[])


@router.patch("/lists/{list_id}", response_model=ListOut, dependencies=[SameOrigin])
async def change_list(
    list_id: uuid.UUID, body: ListIn, user: CurrentUser, session: Session
) -> ListOut:
    row = await _owned(session, user, list_id)
    name = _tidy(body.name)
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the list a name.")
    row.name = name
    if body.position is not None:
        row.position = body.position
    await session.commit()
    return _one(await mine(user, session), row.id)


@router.delete("/lists/{list_id}", status_code=204, dependencies=[SameOrigin])
async def remove_list(list_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    """The list and everything on it."""
    await session.delete(await _owned(session, user, list_id))
    await session.commit()
    return Response(status_code=204)


class SharingIn(BaseModel):
    groups: list[uuid.UUID] = Field(default=[], max_length=50)


@router.put("/lists/{list_id}/groups", response_model=ListOut, dependencies=[SameOrigin])
async def share(
    list_id: uuid.UUID, body: SharingIn, user: CurrentUser, session: Session
) -> ListOut:
    """Choose which of your groups see a list of yours; joining a group
    shares nothing by itself."""
    row = await _owned(session, user, list_id)
    chosen = set(body.groups)
    in_them = set(
        await session.scalars(
            select(GroupMember.group_id).where(
                GroupMember.user_id == user.id, GroupMember.group_id.in_(chosen)
            )
        )
    )
    if chosen - in_them:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You can only share with groups you're in.")
    await session.execute(
        delete(EquipmentListGroup).where(
            EquipmentListGroup.list_id == row.id, EquipmentListGroup.group_id.not_in(chosen)
        )
    )
    held = set(
        await session.scalars(
            select(EquipmentListGroup.group_id).where(EquipmentListGroup.list_id == row.id)
        )
    )
    for group_id in chosen - held:
        session.add(EquipmentListGroup(list_id=row.id, group_id=group_id))
    await session.commit()
    return _one(await mine(user, session), row.id)


class ItemIn(BaseModel):
    name: str = Field(max_length=200)
    # A piece of equipment you chose; matched by name when not given.
    equipment_id: uuid.UUID | None = None
    state: State = "have"


def _thing_named(name: str) -> str:
    """The thing in a name of someone's own: "9-inch springform pan" is a
    springform pan, as it is typed for a recipe (needs.read sets a size
    aside). A name that reads as several things, or as none, is taken
    whole."""
    try:
        read = needs.read(name)
    except needs.Refused:
        return name
    return read.names[0] if read and len(read.names) == 1 else name


async def _matched(session, user: User, name: str, chosen: uuid.UUID | None) -> uuid.UUID | None:
    """The piece of equipment an item is: the one chosen, if you may see it;
    or the one its name is (or is another name for); or none."""
    seen = visibility.equipment_seen_by(user)
    if chosen is not None:
        if await session.scalar(select(Equipment.id).where(Equipment.id == chosen, seen)) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No such equipment.")
        return chosen
    key = match_key(_thing_named(name))
    if not key:
        return None
    by_alias = select(EquipmentAlias.equipment_id).where(
        EquipmentAlias.match_key == key, EquipmentAlias.region.is_(None)
    )
    return await session.scalar(
        select(Equipment.id)
        .where(seen, or_(Equipment.match_key == key, Equipment.id.in_(by_alias)))
        # Its own name before another's other name.
        .order_by(Equipment.match_key != key)
        .limit(1)
    )


@router.post(
    "/lists/{list_id}/items", response_model=ItemOut, status_code=201, dependencies=[SameOrigin]
)
async def add_item(
    list_id: uuid.UUID, body: ItemIn, user: CurrentUser, session: Session
) -> ItemOut:
    row = (await _editable(session, user, list_id)).row
    name = _tidy(body.name)
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Say what it is.")
    # Counted against the list's owner, whoever adds it.
    count = await session.scalar(
        select(func.count())
        .select_from(EquipmentListItem)
        .join(EquipmentList, EquipmentList.id == EquipmentListItem.list_id)
        .where(EquipmentList.owner_id == row.owner_id)
    )
    if count >= MAX_ITEMS:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"At most {MAX_ITEMS} things in your equipment lists."
        )
    item = EquipmentListItem(
        list_id=row.id,
        name=name,
        state=body.state,
        equipment_id=await _matched(session, user, name, body.equipment_id),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return _item(item, await _names(session, user, [item.equipment_id]))


class ItemChange(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    state: State | None = None
    # To another list you may change.
    list_id: uuid.UUID | None = None
    # Choose the piece of equipment it is; "match" sets it from its name
    # again, and "none" leaves it unmatched.
    equipment_id: uuid.UUID | Literal["match", "none"] | None = None


async def _editable_item(session, user: User, item_id: uuid.UUID) -> EquipmentListItem:
    item = await session.get(EquipmentListItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item.")
    await _editable(session, user, item.list_id)
    return item


@router.patch("/items/{item_id}", response_model=ItemOut, dependencies=[SameOrigin])
async def change_item(
    item_id: uuid.UUID, body: ItemChange, user: CurrentUser, session: Session
) -> ItemOut:
    item = await _editable_item(session, user, item_id)
    if body.name is not None:
        name = _tidy(body.name)
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Say what it is.")
        item.name = name
    if body.state is not None:
        item.state = body.state
    if body.list_id is not None:
        item.list_id = (await _editable(session, user, body.list_id)).row.id
    if body.equipment_id == "none":
        item.equipment_id = None
    elif body.equipment_id == "match":
        item.equipment_id = await _matched(session, user, item.name, None)
    elif body.equipment_id is not None:
        item.equipment_id = await _matched(session, user, item.name, body.equipment_id)
    await session.commit()
    await session.refresh(item)
    return _item(item, await _names(session, user, [item.equipment_id]))


@router.delete("/items/{item_id}", status_code=204, dependencies=[SameOrigin])
async def remove_item(item_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    await session.delete(await _editable_item(session, user, item_id))
    await session.commit()
    return Response(status_code=204)
