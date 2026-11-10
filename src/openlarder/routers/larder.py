"""Your larder: lists of what you have (migrations 0046, 0047). *Ray,
2026-11-08 and 2026-11-10.*

Lists are yours to name and order ("Pantry", "Spice drawer"). An item is
your own name for something ("Cholula Chipotle") and the ingredient it is,
matched by name when you add it (an ingredient's name or another name for
it), or chosen. A name that matches nothing stays unmatched: it's kept, and
doesn't count in a search, but it never makes a new ingredient, since a
larder is private and the catalog isn't. Each item is have, running low,
or out: out stays on the list, so you remember it, and doesn't count.

A list is its owner's, and shared with the household groups they choose,
as a private family collection is: a group's view members see it, its edit
and admin members change what's on it. Renaming, removing and sharing a
list stay with its owner. Search with your larder (routers/search.py,
larder=true) counts your lists and those shared with you, each item as
itself and everything above it: Chipotle Hot Sauce is hot sauce too.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select

from openlarder import ingredients, visibility
from openlarder.auth import CurrentUser, SameOrigin
from openlarder.db import Session
from openlarder.models import (
    Group,
    GroupMember,
    Ingredient,
    LarderItem,
    LarderList,
    LarderListGroup,
    User,
)

router = APIRouter(prefix="/api/larder", tags=["larder"])
MAX_LISTS = 50
MAX_ITEMS = 2000
State = Literal["have", "low", "out"]
# Group roles that change what's on a list shared with them.
EDITING_ROLES = ("edit", "admin")


def seen_list_ids(user: User):
    """The lists a person sees: their own, and those shared with a group
    they're in."""
    shared = (
        select(LarderListGroup.list_id)
        .join(GroupMember, GroupMember.group_id == LarderListGroup.group_id)
        .where(GroupMember.user_id == user.id)
    )
    return select(LarderList.id).where(
        or_(LarderList.owner_id == user.id, LarderList.id.in_(shared))
    )


@dataclass
class Access:
    row: LarderList
    owner: bool
    editable: bool


async def _access(session, user: User, list_id: uuid.UUID) -> Access:
    """The list, and what this person may do with it; 404 if they can't see
    it."""
    row = await session.get(LarderList, list_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such list.")
    if row.owner_id == user.id:
        return Access(row, owner=True, editable=True)
    roles = set(
        await session.scalars(
            select(GroupMember.role)
            .join(LarderListGroup, LarderListGroup.group_id == GroupMember.group_id)
            .where(LarderListGroup.list_id == row.id, GroupMember.user_id == user.id)
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


async def _owned(session, user: User, list_id: uuid.UUID) -> LarderList:
    access = await _access(session, user, list_id)
    if not access.owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the list's owner can do that.")
    return access.row


class ItemOut(BaseModel):
    id: uuid.UUID
    list_id: uuid.UUID
    name: str
    state: State
    ingredient_id: uuid.UUID | None
    # The ingredient's name, when there's one you may see.
    ingredient: str | None
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


class Larder(BaseModel):
    lists: list[ListOut]
    # Items that count in a search: have or low, and matched.
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
        select(Ingredient.id, Ingredient.name).where(
            Ingredient.id.in_(ids), visibility.ingredients_seen_by(user)
        )
    )
    return dict(rows.all())


def _item(item: LarderItem, names: dict) -> ItemOut:
    return ItemOut(
        id=item.id,
        list_id=item.list_id,
        name=item.name,
        state=item.state,  # type: ignore[arg-type]
        ingredient_id=item.ingredient_id if item.ingredient_id in names else None,
        ingredient=names.get(item.ingredient_id),
        updated_at=item.updated_at,
    )


@router.get("", response_model=Larder)
async def mine(user: CurrentUser, session: Session) -> Larder:
    """Your lists, then those shared with you."""
    lists = list(
        await session.scalars(
            select(LarderList)
            .where(LarderList.id.in_(seen_list_ids(user)))
            .order_by((LarderList.owner_id != user.id), LarderList.position, LarderList.created_at)
        )
    )
    ids = [lst.id for lst in lists]
    items = list(
        await session.scalars(
            select(LarderItem)
            .where(LarderItem.list_id.in_(ids))
            .order_by(func.lower(LarderItem.name))
        )
    )
    names = await _names(session, user, [i.ingredient_id for i in items])
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
        select(LarderListGroup.list_id, Group.id, Group.name)
        .join(Group, Group.id == LarderListGroup.group_id)
        .where(LarderListGroup.list_id.in_(ids))
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
    return Larder(
        lists=out,
        counted=sum(1 for i in items if i.state != "out" and i.ingredient_id in names),
        groups=[GroupRef(id=i, name=n) for i, n in my_groups.items()],
    )


class ListIn(BaseModel):
    name: str = Field(max_length=100)
    position: int | None = None


def _one(larder: Larder, list_id: uuid.UUID) -> ListOut:
    return next(lst for lst in larder.lists if lst.id == list_id)


@router.post("/lists", response_model=ListOut, status_code=201, dependencies=[SameOrigin])
async def add_list(body: ListIn, user: CurrentUser, session: Session) -> ListOut:
    name = _tidy(body.name)
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the list a name.")
    count = await session.scalar(select(func.count()).where(LarderList.owner_id == user.id))
    if count >= MAX_LISTS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"At most {MAX_LISTS} lists.")
    row = LarderList(owner_id=user.id, name=name, position=body.position or count)
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
        delete(LarderListGroup).where(
            LarderListGroup.list_id == row.id, LarderListGroup.group_id.not_in(chosen)
        )
    )
    held = set(
        await session.scalars(
            select(LarderListGroup.group_id).where(LarderListGroup.list_id == row.id)
        )
    )
    for group_id in chosen - held:
        session.add(LarderListGroup(list_id=row.id, group_id=group_id))
    await session.commit()
    return _one(await mine(user, session), row.id)


class ItemIn(BaseModel):
    name: str = Field(max_length=200)
    # An ingredient you chose; matched by name when not given.
    ingredient_id: uuid.UUID | None = None
    state: State = "have"


async def _matched(session, user: User, name: str, chosen: uuid.UUID | None) -> uuid.UUID | None:
    """The ingredient an item is: the one chosen, if you may see it; or the
    one its name is (or is another name for); or none."""
    seen = visibility.ingredients_seen_by(user)
    if chosen is not None:
        if await session.scalar(select(Ingredient.id).where(Ingredient.id == chosen, seen)) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No such ingredient.")
        return chosen
    key = ingredients.match_key(name)
    found = await ingredients.known(session, {key}, seen)
    return found[key][0] if key in found else None


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
        .select_from(LarderItem)
        .join(LarderList, LarderList.id == LarderItem.list_id)
        .where(LarderList.owner_id == row.owner_id)
    )
    if count >= MAX_ITEMS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"At most {MAX_ITEMS} things in a larder.")
    item = LarderItem(
        list_id=row.id,
        name=name,
        state=body.state,
        ingredient_id=await _matched(session, user, name, body.ingredient_id),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return _item(item, await _names(session, user, [item.ingredient_id]))


class ItemChange(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    state: State | None = None
    # To another list you may change.
    list_id: uuid.UUID | None = None
    # Choose the ingredient it is; "match" sets it from its name again, and
    # "none" leaves it unmatched.
    ingredient_id: uuid.UUID | Literal["match", "none"] | None = None


async def _editable_item(session, user: User, item_id: uuid.UUID) -> LarderItem:
    item = await session.get(LarderItem, item_id)
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
    if body.ingredient_id == "none":
        item.ingredient_id = None
    elif body.ingredient_id == "match":
        item.ingredient_id = await _matched(session, user, item.name, None)
    elif body.ingredient_id is not None:
        item.ingredient_id = await _matched(session, user, item.name, body.ingredient_id)
    await session.commit()
    await session.refresh(item)
    return _item(item, await _names(session, user, [item.ingredient_id]))


@router.delete("/items/{item_id}", status_code=204, dependencies=[SameOrigin])
async def remove_item(item_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    await session.delete(await _editable_item(session, user, item_id))
    await session.commit()
    return Response(status_code=204)
