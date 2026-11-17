"""/go/<retailer>/<edition>: count a buy-link click, then send it on; and
/go/grocer/<grocer>/<ingredient>, the same for an ingredient's grocery
link (grocery.py); /go/equipment/<shop>/<equipment>, the same for a piece
of equipment's shop link (kitchen.py); and /go/producer/<key>, the same for
a producer's (producers.py).

It records the edition, the retailer, the time and the OpenLarder page the
link was on; no user, IP address or cookie, and nothing for a bot. *Ray and
Claude, 2026-11-07 (SCOPING.md, Tracking and disclosure).* Every answer is
no-store: a cached redirect would go uncounted, and Cloudflare caches
whatever doesn't say otherwise.
"""

import uuid

from fastapi import APIRouter, Header, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from openlarder import buying, grocery, kitchen, producers, visibility
from openlarder.auth import Viewer
from openlarder.author_names import shown_name
from openlarder.db import Session
from openlarder.models import (
    Author,
    Edition,
    Equipment,
    EquipmentClick,
    GroceryClick,
    Ingredient,
    ProducerClick,
    PurchaseClick,
    Source,
    SourceCredit,
)

router = APIRouter(tags=["buying"], include_in_schema=False)
NO_STORE = {"Cache-Control": "no-store"}


# Before /go/<retailer>/<edition>, which would take this address for a
# bookseller called "producer" and refuse its key as no edition's id.
@router.get("/go/producer/{key}")
async def go_producer(
    key: str,
    session: Session,
    page: str | None = Query(default=None, alias="from", max_length=2000),
    user_agent: str | None = Header(default=None),
    referer: str | None = Header(default=None),
) -> RedirectResponse:
    target = await producers.destination(session, key)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such link.", headers=NO_STORE)
    if not buying.is_bot(user_agent):
        session.add(ProducerClick(producer=key, page=buying.page_of(page, referer)))
        await session.commit()
    return RedirectResponse(target, status_code=status.HTTP_302_FOUND, headers=NO_STORE)


@router.get("/go/{retailer}/{edition_id}")
async def go(
    retailer: str,
    edition_id: uuid.UUID,
    session: Session,
    page: str | None = Query(default=None, alias="from", max_length=2000),
    user_agent: str | None = Header(default=None),
    referer: str | None = Header(default=None),
) -> RedirectResponse:
    edition = await session.get(Edition, edition_id)
    source = await session.get(Source, edition.source_id) if edition else None
    target = None
    if edition and edition.isbn13 and source and source.kind == "book":
        credit = (
            await session.execute(
                select(SourceCredit.credited_as, Author.name)
                .join(Author, Author.id == SourceCredit.author_id)
                .where(SourceCredit.source_id == source.id)
                .order_by(SourceCredit.position)
                .limit(1)
            )
        ).first()
        target = await buying.destination(
            session,
            retailer,
            buying.Book(
                isbn13=edition.isbn13,
                title=source.title,
                author=shown_name(*credit) if credit else None,
            ),
        )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such link.", headers=NO_STORE)
    if not buying.is_bot(user_agent):
        session.add(
            PurchaseClick(
                edition_id=edition_id,
                retailer=retailer,
                page=buying.page_of(page, referer),
            )
        )
        await session.commit()
    return RedirectResponse(target, status_code=status.HTTP_302_FOUND, headers=NO_STORE)


@router.get("/api/grocers", response_model=list[grocery.GrocerOut], include_in_schema=True)
async def grocers(session: Session) -> list[grocery.GrocerOut]:
    """The grocers an ingredient's link can go to, in the order offered:
    those switched on with their affiliate setting in place."""
    return await grocery.offered(session)


@router.get("/go/grocer/{grocer}/{ingredient_id}")
async def go_grocer(
    grocer: str,
    ingredient_id: uuid.UUID,
    session: Session,
    viewer: Viewer,
    page: str | None = Query(default=None, alias="from", max_length=2000),
    user_agent: str | None = Header(default=None),
    referer: str | None = Header(default=None),
) -> RedirectResponse:
    ingredient = await session.scalar(
        select(Ingredient).where(
            Ingredient.id == ingredient_id, visibility.ingredients_seen_by(viewer)
        )
    )
    target = (
        await grocery.destination(session, grocer, ingredient.shopping_term or ingredient.name)
        if ingredient
        else None
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such link.", headers=NO_STORE)
    if not buying.is_bot(user_agent):
        session.add(
            GroceryClick(
                ingredient_id=ingredient_id, grocer=grocer, page=buying.page_of(page, referer)
            )
        )
        await session.commit()
    return RedirectResponse(target, status_code=status.HTTP_302_FOUND, headers=NO_STORE)


@router.get(
    "/api/kitchen-shops", response_model=list[kitchen.KitchenShopOut], include_in_schema=True
)
async def kitchen_shops(session: Session) -> list[kitchen.KitchenShopOut]:
    """The shops a piece of equipment's link can go to, in the order
    offered: those switched on with their affiliate setting in place."""
    return await kitchen.offered(session)


@router.get("/go/equipment/{shop}/{equipment_id}")
async def go_equipment(
    shop: str,
    equipment_id: uuid.UUID,
    session: Session,
    viewer: Viewer,
    page: str | None = Query(default=None, alias="from", max_length=2000),
    user_agent: str | None = Header(default=None),
    referer: str | None = Header(default=None),
) -> RedirectResponse:
    """As /go/grocer/: only a thing the visitor may see, so the address of
    one a hidden recipe brought in tells nobody its name."""
    thing = await session.scalar(
        select(Equipment).where(Equipment.id == equipment_id, visibility.equipment_seen_by(viewer))
    )
    target = (
        await kitchen.destination(session, shop, thing.shopping_term or thing.name)
        if thing
        else None
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such link.", headers=NO_STORE)
    if not buying.is_bot(user_agent):
        session.add(
            EquipmentClick(equipment_id=equipment_id, shop=shop, page=buying.page_of(page, referer))
        )
        await session.commit()
    return RedirectResponse(target, status_code=status.HTTP_302_FOUND, headers=NO_STORE)
