"""Admin pages for watching the site's outside use: the API's callers
(usage.py) and buy-link clicks (routers/go.py). *Ray, 2026-11-09.*"""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import Date, Text, cast, delete, func, select

from openlarder import buying, grocery, kitchen, producers, usage, visibility
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import (
    ApiKey,
    ApiUsage,
    Edition,
    Equipment,
    EquipmentClick,
    GroceryClick,
    Ingredient,
    ProducerClick,
    PurchaseClick,
    Source,
    User,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
TOP = 20


class Caller(BaseModel):
    caller: str
    # A key's: its name, its start and its owner; or none, for an address.
    key_id: uuid.UUID | None
    key_name: str | None
    key_prefix: str | None
    owner: str | None
    # An address's network (the address itself is never kept).
    network: str | None
    requests: int
    searches: int
    refused: int
    today: int
    last_at: datetime


class UsagePage(BaseModel):
    days: int
    requests: int
    refused: int
    callers: list[Caller]


@router.get("/api-usage", response_model=UsagePage)
async def api_usage(
    admin: AdminUser, session: Session, days: int = Query(7, ge=1, le=usage.RETAIN_DAYS)
) -> UsagePage:
    """Each outside caller over the last few days, busiest first."""
    await usage.flush(session)
    today = datetime.now(UTC).date()
    since = today - timedelta(days=days - 1)
    rows = (
        await session.execute(
            select(
                ApiUsage.caller,
                func.max(cast(ApiUsage.key_id, Text)).label("key_id"),
                func.max(ApiUsage.network),
                func.sum(ApiUsage.requests),
                func.sum(ApiUsage.searches),
                func.sum(ApiUsage.refused),
                func.sum(ApiUsage.requests).filter(ApiUsage.day == today),
                func.max(ApiUsage.last_at),
            )
            .where(ApiUsage.day >= since)
            .group_by(ApiUsage.caller)
            .order_by(func.sum(ApiUsage.requests + ApiUsage.refused).desc())
            .limit(200)
        )
    ).all()
    key_ids = [uuid.UUID(r[1]) for r in rows if r[1]]
    keys = {
        k.id: (k, name)
        for k, name in await session.execute(
            select(ApiKey, User.display_name)
            .join(User, User.id == ApiKey.user_id)
            .where(ApiKey.id.in_(key_ids))
        )
    }
    callers = []
    for caller, key_id, net, requests, searches, refused, today_n, last_at in rows:
        found = keys.get(uuid.UUID(key_id)) if key_id else None
        callers.append(
            Caller(
                caller=caller,
                key_id=found[0].id if found else None,
                key_name=found[0].name
                if found
                else ("A revoked key" if caller.startswith("key:") else None),
                key_prefix=found[0].prefix if found else None,
                owner=found[1] if found else None,
                network=net,
                requests=requests or 0,
                searches=searches or 0,
                refused=refused or 0,
                today=today_n or 0,
                last_at=last_at,
            )
        )
    return UsagePage(
        days=days,
        requests=sum(c.requests for c in callers),
        refused=sum(c.refused for c in callers),
        callers=callers,
    )


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SameOrigin])
async def revoke_any_key(key_id: uuid.UUID, admin: AdminUser, session: Session) -> Response:
    """An admin revokes a key being misused; its usage stays, as a revoked key's."""
    found = await session.execute(delete(ApiKey).where(ApiKey.id == key_id))
    if not found.rowcount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such key.")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ShopClicks(BaseModel):
    retailer: str
    label: str
    clicks: int
    last_7_days: int


class BookClicks(BaseModel):
    source_id: uuid.UUID
    title: str
    isbn13: str | None
    clicks: int


class PageClicks(BaseModel):
    page: str | None
    clicks: int


class DayClicks(BaseModel):
    day: date
    clicks: int


class IngredientClicks(BaseModel):
    ingredient_id: uuid.UUID
    name: str
    clicks: int


class EquipmentClicks(BaseModel):
    equipment_id: uuid.UUID
    name: str
    clicks: int


class ClicksPage(BaseModel):
    days: int
    clicks: int
    shops: list[ShopClicks]
    books: list[BookClicks]
    pages: list[PageClicks]
    by_day: list[DayClicks]
    # Ingredients' grocery links (grocery.py): by grocer, and the most
    # clicked ingredients.
    grocery_clicks: int = 0
    grocers: list[ShopClicks] = []
    ingredients: list[IngredientClicks] = []
    # Producers' links (producers.py), by producer.
    producer_clicks: int = 0
    producers: list[ShopClicks] = []
    # Equipment's shop links (kitchen.py): by shop, and the most clicked
    # things, as the grocery links are.
    equipment_clicks: int = 0
    kitchen_shops: list[ShopClicks] = []
    equipment: list[EquipmentClicks] = []


@router.get("/clicks", response_model=ClicksPage)
async def clicks(
    admin: AdminUser, session: Session, days: int = Query(30, ge=1, le=366)
) -> ClicksPage:
    """Buy-link clicks: by shop, by book, by the page they were on, by day."""
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    week = now - timedelta(days=7)
    window = PurchaseClick.clicked_at >= since
    shops = (
        await session.execute(
            select(
                PurchaseClick.retailer,
                func.count(),
                func.count().filter(PurchaseClick.clicked_at >= week),
            )
            .where(window)
            .group_by(PurchaseClick.retailer)
            .order_by(func.count().desc())
        )
    ).all()
    books = (
        await session.execute(
            select(Source.id, Source.title, Edition.isbn13, func.count())
            .select_from(PurchaseClick)
            .join(Edition, Edition.id == PurchaseClick.edition_id)
            .join(Source, Source.id == Edition.source_id)
            .where(window)
            .group_by(Source.id, Source.title, Edition.isbn13)
            .order_by(func.count().desc(), Source.title)
            .limit(TOP)
        )
    ).all()
    pages = (
        await session.execute(
            select(PurchaseClick.page, func.count())
            .where(window)
            .group_by(PurchaseClick.page)
            .order_by(func.count().desc())
            .limit(TOP)
        )
    ).all()
    day = cast(func.timezone("UTC", PurchaseClick.clicked_at), Date)
    by_day = (
        await session.execute(select(day, func.count()).where(window).group_by(day).order_by(day))
    ).all()
    labels = await buying.labels(session)
    in_window = GroceryClick.clicked_at >= since
    grocers = (
        await session.execute(
            select(
                GroceryClick.grocer,
                func.count(),
                func.count().filter(GroceryClick.clicked_at >= week),
            )
            .where(in_window)
            .group_by(GroceryClick.grocer)
            .order_by(func.count().desc())
        )
    ).all()
    top_ingredients = (
        await session.execute(
            select(Ingredient.id, Ingredient.name, func.count())
            .select_from(GroceryClick)
            .join(Ingredient, Ingredient.id == GroceryClick.ingredient_id)
            .where(in_window, visibility.ingredients_seen_by(admin))
            .group_by(Ingredient.id, Ingredient.name)
            .order_by(func.count().desc(), Ingredient.name)
            .limit(TOP)
        )
    ).all()
    grocer_labels = await grocery.labels(session)
    by_producer = (
        await session.execute(
            select(
                ProducerClick.producer,
                func.count(),
                func.count().filter(ProducerClick.clicked_at >= week),
            )
            .where(ProducerClick.clicked_at >= since)
            .group_by(ProducerClick.producer)
            .order_by(func.count().desc())
        )
    ).all()
    producer_labels = await producers.labels(session)
    on_equipment = EquipmentClick.clicked_at >= since
    by_kitchen_shop = (
        await session.execute(
            select(
                EquipmentClick.shop,
                func.count(),
                func.count().filter(EquipmentClick.clicked_at >= week),
            )
            .where(on_equipment)
            .group_by(EquipmentClick.shop)
            .order_by(func.count().desc())
        )
    ).all()
    top_equipment = (
        await session.execute(
            select(Equipment.id, Equipment.name, func.count())
            .select_from(EquipmentClick)
            .join(Equipment, Equipment.id == EquipmentClick.equipment_id)
            # A thing a hidden recipe brought in isn't named to an
            # administrator who can't see that recipe.
            .where(on_equipment, visibility.equipment_seen_by(admin))
            .group_by(Equipment.id, Equipment.name)
            .order_by(func.count().desc(), Equipment.name)
            .limit(TOP)
        )
    ).all()
    kitchen_labels = await kitchen.labels(session)
    return ClicksPage(
        equipment_clicks=sum(n for _, n, _ in by_kitchen_shop),
        kitchen_shops=[
            ShopClicks(retailer=k, label=kitchen_labels.get(k, k), clicks=n, last_7_days=w)
            for k, n, w in by_kitchen_shop
        ],
        equipment=[EquipmentClicks(equipment_id=i, name=m, clicks=n) for i, m, n in top_equipment],
        producer_clicks=sum(n for _, n, _ in by_producer),
        producers=[
            ShopClicks(retailer=p, label=producer_labels.get(p, p), clicks=n, last_7_days=w)
            for p, n, w in by_producer
        ],
        grocery_clicks=sum(n for _, n, _ in grocers),
        grocers=[
            ShopClicks(retailer=g, label=grocer_labels.get(g, g), clicks=n, last_7_days=w)
            for g, n, w in grocers
        ],
        ingredients=[
            IngredientClicks(ingredient_id=i, name=m, clicks=n) for i, m, n in top_ingredients
        ],
        days=days,
        clicks=sum(n for _, n, _ in shops),
        shops=[
            ShopClicks(retailer=r, label=labels.get(r, r), clicks=n, last_7_days=w)
            for r, n, w in shops
        ],
        books=[BookClicks(source_id=i, title=t, isbn13=isbn, clicks=n) for i, t, isbn, n in books],
        pages=[PageClicks(page=p, clicks=n) for p, n in pages],
        by_day=[DayClicks(day=d, clicks=n) for d, n in by_day],
    )
