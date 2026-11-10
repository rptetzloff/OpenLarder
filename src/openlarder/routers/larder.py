"""Your larder: lists of what you have (migration 0046). *Ray, 2026-11-08
and 2026-11-10.*

Lists are yours to name and order ("Pantry", "Spice drawer"). An item is
your own name for something ("Cholula Chipotle") and the ingredient it is,
matched by name when you add it (an ingredient's name or another name for
it), or chosen. A name that matches nothing stays unmatched: it's kept, and
doesn't count in a search, but it never makes a new ingredient, since a
larder is private and the catalog isn't. Each item is have, running low,
or out: out stays on the list, so you remember it, and doesn't count.

Search with your larder (routers/search.py, larder=true) counts each item
as itself and everything above it: Chipotle Hot Sauce is hot sauce too.

Only its owner sees a larder; sharing through household groups comes next.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from openlarder import ingredients, visibility
from openlarder.auth import CurrentUser, SameOrigin
from openlarder.db import Session
from openlarder.models import Ingredient, LarderItem, LarderList, User

router = APIRouter(prefix="/api/larder", tags=["larder"])
MAX_LISTS = 50
MAX_ITEMS = 2000
State = Literal["have", "low", "out"]


class ItemOut(BaseModel):
    id: uuid.UUID
    list_id: uuid.UUID
    name: str
    state: State
    ingredient_id: uuid.UUID | None
    # The ingredient's name, when there's one you may see.
    ingredient: str | None
    updated_at: datetime


class ListOut(BaseModel):
    id: uuid.UUID
    name: str
    position: int
    items: list[ItemOut]


class Larder(BaseModel):
    lists: list[ListOut]
    # Items that count in a search: have or low, and matched.
    counted: int


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
    lists = list(
        await session.scalars(
            select(LarderList)
            .where(LarderList.owner_id == user.id)
            .order_by(LarderList.position, LarderList.created_at)
        )
    )
    items = list(
        await session.scalars(
            select(LarderItem)
            .where(LarderItem.list_id.in_([lst.id for lst in lists]))
            .order_by(func.lower(LarderItem.name))
        )
    )
    names = await _names(session, user, [i.ingredient_id for i in items])
    by_list: dict[uuid.UUID, list[ItemOut]] = {}
    for item in items:
        by_list.setdefault(item.list_id, []).append(_item(item, names))
    return Larder(
        lists=[
            ListOut(id=lst.id, name=lst.name, position=lst.position, items=by_list.get(lst.id, []))
            for lst in lists
        ],
        counted=sum(1 for i in items if i.state != "out" and i.ingredient_id in names),
    )


class ListIn(BaseModel):
    name: str = Field(max_length=100)
    position: int | None = None


async def _list(session, user: User, list_id: uuid.UUID) -> LarderList:
    found = await session.get(LarderList, list_id)
    if found is None or found.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such list.")
    return found


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
    row = await _list(session, user, list_id)
    name = _tidy(body.name)
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the list a name.")
    row.name = name
    if body.position is not None:
        row.position = body.position
    await session.commit()
    larder = await mine(user, session)
    return next(lst for lst in larder.lists if lst.id == row.id)


@router.delete("/lists/{list_id}", status_code=204, dependencies=[SameOrigin])
async def remove_list(list_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    """The list and everything on it."""
    await session.delete(await _list(session, user, list_id))
    await session.commit()
    return Response(status_code=204)


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
    row = await _list(session, user, list_id)
    name = _tidy(body.name)
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Say what it is.")
    count = await session.scalar(
        select(func.count())
        .select_from(LarderItem)
        .join(LarderList, LarderList.id == LarderItem.list_id)
        .where(LarderList.owner_id == user.id)
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
    # To another of your lists.
    list_id: uuid.UUID | None = None
    # Choose the ingredient it is; "match" sets it from its name again, and
    # "none" leaves it unmatched.
    ingredient_id: uuid.UUID | Literal["match", "none"] | None = None


async def _owned_item(session, user: User, item_id: uuid.UUID) -> LarderItem:
    item = await session.get(LarderItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item.")
    await _list(session, user, item.list_id)
    return item


@router.patch("/items/{item_id}", response_model=ItemOut, dependencies=[SameOrigin])
async def change_item(
    item_id: uuid.UUID, body: ItemChange, user: CurrentUser, session: Session
) -> ItemOut:
    item = await _owned_item(session, user, item_id)
    if body.name is not None:
        name = _tidy(body.name)
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Say what it is.")
        item.name = name
    if body.state is not None:
        item.state = body.state
    if body.list_id is not None:
        item.list_id = (await _list(session, user, body.list_id)).id
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
    await session.delete(await _owned_item(session, user, item_id))
    await session.commit()
    return Response(status_code=204)
