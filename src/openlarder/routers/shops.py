"""Shops, for administrators: the booksellers, grocers, producers and
kitchen shops a link
out of the site can go to, added, changed, put in order and switched on
and off from the site, with no redeploy (shops.py; round 4, part D).

*Decided by Ray, 2026-11-13.* Administrators only, not moderators: an
affiliate id or a deep link is no secret, since every link the site sends
shows it, but whoever sets one says where /go/ sends people.

Every change is in the edit history, with who and when (migration 0074),
and this process reads the shops again at once; the others within a minute.
A shop with clicks recorded is switched off, never deleted, so the clicks
keep their meaning.

A producer (producers.py) has what the others haven't: a description, an
offer, the states it ships to and the ingredients it supplies. Its address
is its referral link, as written. Switched on, it must say beside its link
what is earned and by whom, unless nothing is. The ingredients it supplies
are ones everyone can see: one that only a private family collection uses
is refused, so its name can't reach a public page from here.
"""

import re
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import producers, shops, visibility
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import (
    EquipmentClick,
    GroceryClick,
    Ingredient,
    ProducerClick,
    ProducerIngredient,
    PurchaseClick,
    User,
)
from openlarder.models import Shop as ShopRow

router = APIRouter(prefix="/api/admin/shops", tags=["admin"])

Kind = Literal["bookseller", "grocer", "producer", "kitchen"]
Builder = Literal["bookshop", "amazon", "wrapped", "template", "direct"]
_KEY = re.compile(r"[a-z0-9-]{1,40}")
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
KINDS = {
    "bookseller": "Booksellers",
    "grocer": "Grocers",
    "producer": "Producers",
    "kitchen": "Kitchen shops",
}
# Not a bookseller's key: /go/producer/<key> is the producers' address, and
# /go/<bookseller>/<edition> would be shadowed by it.
RESERVED = {"bookseller": {"producer"}}


class ShopOut(BaseModel):
    id: uuid.UUID
    key: str
    kind: str
    label: str
    builder: str
    affiliate_id: str | None
    wrapper_template: str | None
    product_template: str | None
    format: str | None
    earns: str
    note: str | None
    enabled: bool
    # Shown on the site now: switched on, with what its builder needs.
    shown: bool
    # Switched on and not shown: what it still needs.
    needs: str | None
    # Producers only: what it is, what a new customer gets, the states it
    # ships to (none: everywhere), and the ingredients it supplies.
    description: str | None = None
    offer: str | None = None
    ships_to: list[str] | None = None
    supplies: list[producers.Named] = []
    clicks_30_days: int
    # Clicks ever: with any, it's switched off and not deleted.
    clicks: int
    updated_at: datetime
    # Who last changed it; none while it's as it was first set up.
    updated_by: str | None


class Group(BaseModel):
    kind: str
    label: str
    shops: list[ShopOut]


class Fields(BaseModel):
    """What can be changed on a shop."""

    label: str = Field(max_length=100)
    builder: Builder
    affiliate_id: str | None = Field(default=None, max_length=200)
    wrapper_template: str | None = Field(default=None, max_length=2000)
    product_template: str | None = Field(default=None, max_length=2000)
    format: Literal["print", "ebook"] | None = None
    earns: Literal["affiliate", "referral", "none"] = "affiliate"
    note: str | None = Field(default=None, max_length=300)
    enabled: bool = False
    # Producers only.
    description: str | None = Field(default=None, max_length=600)
    offer: str | None = Field(default=None, max_length=200)
    ships_to: list[str] | None = Field(default=None, max_length=60)
    supplies: list[uuid.UUID] = Field(default=[], max_length=200)


class NewShop(Fields):
    key: str = Field(max_length=40)
    kind: Kind


def _refuse(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def _checked(kind: str, body: Fields) -> dict:
    """The fields as they'll be stored, or a refusal that says what's wrong:
    what config.py asked of the environment variables these replaced."""
    label = " ".join(body.label.split())
    if not label:
        raise _refuse("Give the shop a name.")
    if body.builder not in shops.BUILDERS[kind]:
        raise _refuse(f"A {kind}'s address can't be made that way.")
    affiliate, wrapper = _clean(body.affiliate_id), _clean(body.wrapper_template)
    product, note = _clean(body.product_template), _clean(body.note)
    if affiliate is not None:
        if body.builder == "bookshop" and not affiliate.isdigit():
            raise _refuse("Bookshop.org's affiliate id is a number, like 12345.")
        if body.builder == "amazon" and not _TAG.fullmatch(affiliate):
            raise _refuse("An Associates tag is letters, digits and hyphens, like openlarder-20.")
        if not re.fullmatch(r"\S+", affiliate):
            raise _refuse("An affiliate id has no spaces in it.")
    if wrapper is not None:
        if not wrapper.startswith("https://"):
            raise _refuse("The network's deep link starts https://.")
        if _PLACEHOLDER.findall(wrapper) != ["url"]:
            raise _refuse("The network's deep link has {url} once, where the shop's address goes.")
    if product is not None:
        if not product.startswith("https://"):
            raise _refuse("The shop's address starts https://.")
        if re.search(r"\s", product):
            raise _refuse("The shop's address has no spaces in it.")
        allowed = shops.PLACEHOLDERS[kind]
        unknown = [p for p in _PLACEHOLDER.findall(product) if p not in allowed]
        if unknown and not allowed:
            raise _refuse(
                "A producer's address is its referral link, used as written: it has no"
                f" {{{unknown[0]}}} in it."
            )
        if unknown:
            raise _refuse(
                f"The shop's address has {{{unknown[0]}}}, which isn't one of"
                f" {', '.join('{' + p + '}' for p in allowed)}."
            )
    if body.builder == "amazon":
        # Its address is made in code.
        product = wrapper = None
    if body.builder != "wrapped":
        wrapper = None
    format_ = (body.format or "print") if kind == "bookseller" else None
    description = offer = ships_to = None
    if kind == "producer":
        affiliate = None
        description = " ".join((body.description or "").split()) or None
        offer = " ".join((body.offer or "").split()) or None
        ships_to = _states(body.ships_to)
    return {
        "label": label,
        "builder": body.builder,
        "affiliate_id": affiliate,
        "wrapper_template": wrapper,
        "product_template": product,
        "format": format_,
        "earns": body.earns,
        "note": note,
        "enabled": body.enabled,
        "description": description,
        "offer": offer,
        "ships_to": ships_to,
    }


def _states(given: list[str] | None) -> list[str] | None:
    """The states a producer ships to, as their codes in order; None for
    none given, which is everywhere."""
    codes = sorted({code.strip().upper() for code in given or [] if code.strip()})
    if unknown := [code for code in codes if code not in producers.STATES]:
        raise _refuse(f"“{unknown[0]}” isn't a state's two-letter code. Give them like WI, MN, IL.")
    return codes or None


def _as_shop(kind: str, key: str, fields: dict) -> shops.Shop:
    ships_to = fields["ships_to"]
    return shops.Shop(
        key=key,
        kind=kind,
        position=0,
        **{**fields, "ships_to": tuple(ships_to) if ships_to is not None else None},
    )


def _must_be_whole(shop: shops.Shop) -> None:
    """A shop switched on has what its builder needs: one that can't make a
    link would be on, and not there."""
    if shop.enabled and (needs := shops.lacks(shop)):
        raise _refuse(f"Switched on, it needs {needs}. Give it that, or leave it off.")
    if shop.enabled and shops.sample(shop) is None:
        raise _refuse("Its address can't be made for a book. Check what the address asks for.")
    if shop.enabled and shop.kind == "producer" and shop.earns != "none" and not shop.note:
        raise _refuse(
            "Switched on, a producer says beside its link what is earned and by whom."
            " Write that, or say a click earns nothing."
        )


async def _may_supply(session: AsyncSession, wanted: list[uuid.UUID]) -> set[uuid.UUID]:
    """The ingredients asked for, if each is one everyone can see. Asked
    before anything is written, so a refusal leaves nothing half done."""
    asked = set(wanted)
    if asked:
        seen = set(
            await session.scalars(
                select(Ingredient.id).where(
                    Ingredient.id.in_(asked), visibility.ingredients_seen_by(None)
                )
            )
        )
        if seen != asked:
            raise _refuse(
                "One of those ingredients isn't in the catalog everyone sees. Take it off"
                " and pick it again."
            )
    return asked


async def _supply(session: AsyncSession, shop_id: uuid.UUID, asked: set[uuid.UUID]) -> None:
    """The ingredients a producer supplies, made to be these."""
    had = set(
        await session.scalars(
            select(ProducerIngredient.ingredient_id).where(ProducerIngredient.shop_id == shop_id)
        )
    )
    if gone := had - asked:
        await session.execute(
            delete(ProducerIngredient).where(
                ProducerIngredient.shop_id == shop_id,
                ProducerIngredient.ingredient_id.in_(gone),
            )
        )
    for ingredient_id in sorted(asked - had):
        session.add(ProducerIngredient(shop_id=shop_id, ingredient_id=ingredient_id))


async def _clicks(
    session: AsyncSession, since: datetime | None = None
) -> dict[tuple[str, str], int]:
    """Clicks by (kind, key): ever, or since a time."""
    found: dict[tuple[str, str], int] = {}
    for kind, model, column in (
        ("bookseller", PurchaseClick, PurchaseClick.retailer),
        ("grocer", GroceryClick, GroceryClick.grocer),
        ("producer", ProducerClick, ProducerClick.producer),
        ("kitchen", EquipmentClick, EquipmentClick.shop),
    ):
        query = select(column, func.count()).group_by(column)
        if since is not None:
            query = query.where(model.clicked_at >= since)
        for key, n in await session.execute(query):
            found[kind, key] = n
    return found


async def _supplied(session: AsyncSession, viewer: User) -> dict[uuid.UUID, list]:
    """What each producer supplies, by name, as this administrator may see
    them: an ingredient that has become a private collection's alone since
    it was picked isn't named to someone who can't see that collection."""
    found: dict[uuid.UUID, list] = {}
    rows = await session.execute(
        select(ProducerIngredient.shop_id, Ingredient.id, Ingredient.name)
        .join(Ingredient, Ingredient.id == ProducerIngredient.ingredient_id)
        .where(visibility.ingredients_seen_by(viewer))
        .order_by(Ingredient.name)
    )
    for shop_id, ingredient_id, name in rows:
        found.setdefault(shop_id, []).append(producers.Named(id=ingredient_id, name=name))
    return found


async def _out(session: AsyncSession, viewer: User) -> list[Group]:
    rows = {
        (r.kind, r.key): r
        for r in await session.scalars(select(ShopRow).where(ShopRow.kind.in_(KINDS)))
    }
    names = dict(
        (
            await session.execute(
                select(User.id, User.display_name).where(
                    User.id.in_({r.updated_by for r in rows.values() if r.updated_by})
                )
            )
        ).all()
    )
    ever = await _clicks(session)
    lately = await _clicks(session, datetime.now(UTC) - timedelta(days=30))
    supplied = await _supplied(session, viewer)
    groups = []
    for kind, label in KINDS.items():
        listed = []
        for s in await shops.listed(session, kind):
            row = rows[kind, s.key]
            needs = shops.lacks(s) if s.enabled else None
            listed.append(
                ShopOut(
                    id=row.id,
                    key=s.key,
                    kind=s.kind,
                    label=s.label,
                    builder=s.builder,
                    affiliate_id=s.affiliate_id,
                    wrapper_template=s.wrapper_template,
                    product_template=s.product_template,
                    format=s.format,
                    earns=s.earns,
                    note=s.note,
                    enabled=s.enabled,
                    shown=s.enabled and shops.sample(s) is not None,
                    needs=needs,
                    description=s.description,
                    offer=s.offer,
                    ships_to=list(s.ships_to) if s.ships_to is not None else None,
                    supplies=supplied.get(row.id, []),
                    clicks_30_days=lately.get((kind, s.key), 0),
                    clicks=ever.get((kind, s.key), 0),
                    updated_at=row.updated_at,
                    updated_by=names.get(row.updated_by) if row.updated_by else None,
                )
            )
        groups.append(Group(kind=kind, label=label, shops=listed))
    return groups


async def _fresh(session: AsyncSession, viewer: User) -> list[Group]:
    """After a change: saved, this process's shops forgotten, and the list."""
    await session.commit()
    shops.reset()
    return await _out(session, viewer)


async def _row_or_404(session: AsyncSession, shop_id: uuid.UUID) -> ShopRow:
    row = await session.get(ShopRow, shop_id)
    if row is None or row.kind not in KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shop.")
    return row


@router.get("", response_model=list[Group])
async def list_shops(admin: AdminUser, session: Session) -> list[Group]:
    """Every bookseller, grocer and producer, in the order shown, with its
    clicks in the last 30 days and who last changed it."""
    return await _out(session, admin)


@router.post("", response_model=list[Group], dependencies=[SameOrigin])
async def add_shop(body: NewShop, admin: AdminUser, session: Session) -> list[Group]:
    """A new shop, last among its kind. Its key is for good: it's in the
    shop's /go/ addresses and its click records."""
    key = body.key.strip()
    if not _KEY.fullmatch(key):
        raise _refuse("A key is lowercase letters, digits and hyphens, like corner-shop.")
    if key in RESERVED.get(body.kind, ()):
        raise _refuse(f"“{key}” is taken by the site's own addresses. Choose another.")
    taken = await session.scalar(
        select(ShopRow).where(ShopRow.kind == body.kind, ShopRow.key == key)
    )
    if taken is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"“{key}” is {taken.label}'s key. Choose another."
        )
    fields = _checked(body.kind, body)
    _must_be_whole(_as_shop(body.kind, key, fields))
    supplies = await _may_supply(session, body.supplies) if body.kind == "producer" else set()
    last = await session.scalar(select(func.max(ShopRow.position)).where(ShopRow.kind == body.kind))
    row = ShopRow(
        key=key,
        kind=body.kind,
        position=(last if last is not None else -1) + 1,
        updated_by=admin.id,
        **fields,
    )
    session.add(row)
    if body.kind == "producer":
        await session.flush()
        await _supply(session, row.id, supplies)
    return await _fresh(session, admin)


@router.put("/{shop_id}", response_model=list[Group], dependencies=[SameOrigin])
async def change_shop(
    shop_id: uuid.UUID, body: Fields, admin: AdminUser, session: Session
) -> list[Group]:
    """A shop as it's now to be: all of its fields but its key and kind."""
    row = await _row_or_404(session, shop_id)
    fields = _checked(row.kind, body)
    _must_be_whole(_as_shop(row.kind, row.key, fields))
    supplies = await _may_supply(session, body.supplies) if row.kind == "producer" else set()
    for name, value in fields.items():
        setattr(row, name, value)
    if row.kind == "producer":
        await _supply(session, row.id, supplies)
    row.updated_by = admin.id
    row.updated_at = datetime.now(UTC)
    return await _fresh(session, admin)


class Switch(BaseModel):
    enabled: bool


@router.put("/{shop_id}/enabled", response_model=list[Group], dependencies=[SameOrigin])
async def switch_shop(
    shop_id: uuid.UUID, body: Switch, admin: AdminUser, session: Session
) -> list[Group]:
    """On or off, without the rest of the form."""
    row = await _row_or_404(session, shop_id)
    now = await shops.find(session, row.kind, row.key)
    row.enabled = body.enabled
    if now:
        _must_be_whole(replace(now, enabled=body.enabled))
    row.updated_by = admin.id
    row.updated_at = datetime.now(UTC)
    return await _fresh(session, admin)


class Move(BaseModel):
    to: Literal["up", "down"]


@router.post("/{shop_id}/move", response_model=list[Group], dependencies=[SameOrigin])
async def move_shop(
    shop_id: uuid.UUID, body: Move, admin: AdminUser, session: Session
) -> list[Group]:
    """One place up or down among its kind. Past either end, nothing moves."""
    row = await _row_or_404(session, shop_id)
    order = list(
        await session.scalars(
            select(ShopRow).where(ShopRow.kind == row.kind).order_by(ShopRow.position, ShopRow.key)
        )
    )
    at = next(n for n, r in enumerate(order) if r.id == row.id)
    to = at - 1 if body.to == "up" else at + 1
    if 0 <= to < len(order):
        order[at], order[to] = order[to], order[at]
        # Renumbered, so two with the same position can't be stuck together.
        for n, r in enumerate(order):
            if r.position != n:
                r.position = n
        row.updated_by = admin.id
        row.updated_at = datetime.now(UTC)
    return await _fresh(session, admin)


@router.delete("/{shop_id}", response_model=list[Group], dependencies=[SameOrigin])
async def remove_shop(shop_id: uuid.UUID, admin: AdminUser, session: Session) -> list[Group]:
    """Takes a shop away for good: one nobody has clicked. With clicks
    recorded it's switched off instead, so they still say which shop."""
    row = await _row_or_404(session, shop_id)
    clicks = (await _clicks(session)).get((row.kind, row.key), 0)
    if clicks:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{row.label} has {clicks:,} {'click' if clicks == 1 else 'clicks'} recorded."
            " Switch it off instead, so they keep their meaning.",
        )
    await session.delete(row)
    return await _fresh(session, admin)


class Tried(BaseModel):
    # Where a click would go, for the sample; and its host, to look at.
    url: str
    host: str
    # What it was made for.
    sample: str


@router.post("/test", response_model=Tried, dependencies=[SameOrigin])
async def test_link(body: NewShop, admin: AdminUser) -> Tried | Response:
    """Where a shop set up like this would send a click, for a sample book
    or ingredient. Nothing is saved, and it doesn't go through /go/, so no
    click is counted."""
    fields = _checked(body.kind, body)
    shop = _as_shop(body.kind, body.key.strip() or "new", {**fields, "enabled": True})
    if needs := shops.lacks(shop):
        raise _refuse(f"It needs {needs} before there's a link to try.")
    url = shops.sample(shop)
    if url is None:
        raise _refuse("Its address can't be made for the sample. Check what the address asks for.")
    book = shops.SAMPLE_BOOK
    return Tried(
        url=url,
        host=urlsplit(url).hostname or "",
        sample={
            "bookseller": f"“{book.title}” by {book.author}, ISBN {book.isbn13}",
            "grocer": f"the ingredient “{shops.SAMPLE_TERM}”",
            "producer": "anyone who follows it",
            "kitchen": f"the equipment “{shops.SAMPLE_EQUIPMENT}”",
        }[body.kind],
    )
