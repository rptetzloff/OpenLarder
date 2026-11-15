"""Shops, for administrators: the booksellers and grocers a link out of the
site can go to, added, changed, put in order and switched on and off from
the site, with no redeploy (shops.py; round 4, part D).

*Decided by Ray, 2026-11-13.* Administrators only, not moderators: an
affiliate id or a deep link is no secret, since every link the site sends
shows it, but whoever sets one says where /go/ sends people.

Every change is in the edit history, with who and when (migration 0074),
and this process reads the shops again at once; the others within a minute.
A shop with clicks recorded is switched off, never deleted, so the clicks
keep their meaning.
"""

import re
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import shops
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import GroceryClick, PurchaseClick, User
from openlarder.models import Shop as ShopRow

router = APIRouter(prefix="/api/admin/shops", tags=["admin"])

Kind = Literal["bookseller", "grocer"]
Builder = Literal["bookshop", "amazon", "wrapped", "template"]
_KEY = re.compile(r"[a-z0-9-]{1,40}")
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
KINDS = {"bookseller": "Booksellers", "grocer": "Grocers"}


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
    # Its setting is still in this environment variable and not on the shop;
    # saving it here puts it on the shop.
    variable: str | None
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


class NewShop(Fields):
    key: str = Field(max_length=40)
    kind: Kind


def _refuse(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def _checked(kind: str, body: Fields) -> dict:
    """The fields as they'll be stored, or a refusal that says what's wrong:
    what config.py asked of the environment variables these replace."""
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
        allowed = shops.PLACEHOLDERS[kind]
        if unknown := [p for p in _PLACEHOLDER.findall(product) if p not in allowed]:
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
    }


def _as_shop(kind: str, key: str, fields: dict) -> shops.Shop:
    return shops.Shop(key=key, kind=kind, position=0, **fields)


def _must_be_whole(shop: shops.Shop) -> None:
    """A shop switched on has what its builder needs: one that can't make a
    link would be on, and not there."""
    if shop.enabled and (needs := shops.lacks(shop)):
        raise _refuse(f"Switched on, it needs {needs}. Give it that, or leave it off.")
    if shop.enabled and shops.sample(shop) is None:
        raise _refuse("Its address can't be made for a book. Check what the address asks for.")


async def _clicks(
    session: AsyncSession, since: datetime | None = None
) -> dict[tuple[str, str], int]:
    """Clicks by (kind, key): ever, or since a time."""
    found: dict[tuple[str, str], int] = {}
    for kind, model, column in (
        ("bookseller", PurchaseClick, PurchaseClick.retailer),
        ("grocer", GroceryClick, GroceryClick.grocer),
    ):
        query = select(column, func.count()).group_by(column)
        if since is not None:
            query = query.where(model.clicked_at >= since)
        for key, n in await session.execute(query):
            found[kind, key] = n
    return found


async def _out(session: AsyncSession) -> list[Group]:
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
    groups = []
    for kind, label in KINDS.items():
        listed = []
        # As the site has them: with a setting still in its variable.
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
                    variable=s.variable,
                    clicks_30_days=lately.get((kind, s.key), 0),
                    clicks=ever.get((kind, s.key), 0),
                    updated_at=row.updated_at,
                    updated_by=names.get(row.updated_by) if row.updated_by else None,
                )
            )
        groups.append(Group(kind=kind, label=label, shops=listed))
    return groups


async def _fresh(session: AsyncSession) -> list[Group]:
    """After a change: saved, this process's shops forgotten, and the list."""
    await session.commit()
    shops.reset()
    return await _out(session)


async def _row_or_404(session: AsyncSession, shop_id: uuid.UUID) -> ShopRow:
    row = await session.get(ShopRow, shop_id)
    if row is None or row.kind not in KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shop.")
    return row


@router.get("", response_model=list[Group])
async def list_shops(admin: AdminUser, session: Session) -> list[Group]:
    """Every bookseller and grocer, in the order shown, with its clicks in
    the last 30 days and who last changed it."""
    return await _out(session)


@router.post("", response_model=list[Group], dependencies=[SameOrigin])
async def add_shop(body: NewShop, admin: AdminUser, session: Session) -> list[Group]:
    """A new shop, last among its kind. Its key is for good: it's in the
    shop's /go/ addresses and its click records."""
    key = body.key.strip()
    if not _KEY.fullmatch(key):
        raise _refuse("A key is lowercase letters, digits and hyphens, like corner-shop.")
    taken = await session.scalar(
        select(ShopRow).where(ShopRow.kind == body.kind, ShopRow.key == key)
    )
    if taken is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"“{key}” is {taken.label}'s key. Choose another."
        )
    fields = _checked(body.kind, body)
    _must_be_whole(_as_shop(body.kind, key, fields))
    last = await session.scalar(select(func.max(ShopRow.position)).where(ShopRow.kind == body.kind))
    session.add(
        ShopRow(
            key=key,
            kind=body.kind,
            position=(last if last is not None else -1) + 1,
            updated_by=admin.id,
            **fields,
        )
    )
    return await _fresh(session)


@router.put("/{shop_id}", response_model=list[Group], dependencies=[SameOrigin])
async def change_shop(
    shop_id: uuid.UUID, body: Fields, admin: AdminUser, session: Session
) -> list[Group]:
    """A shop as it's now to be: all of its fields but its key and kind."""
    row = await _row_or_404(session, shop_id)
    fields = _checked(row.kind, body)
    _must_be_whole(_as_shop(row.kind, row.key, fields))
    for name, value in fields.items():
        setattr(row, name, value)
    row.updated_by = admin.id
    row.updated_at = datetime.now(UTC)
    return await _fresh(session)


class Switch(BaseModel):
    enabled: bool


@router.put("/{shop_id}/enabled", response_model=list[Group], dependencies=[SameOrigin])
async def switch_shop(
    shop_id: uuid.UUID, body: Switch, admin: AdminUser, session: Session
) -> list[Group]:
    """On or off, without the rest of the form. Switched on from a setting
    still in its environment variable, the setting is put on the shop."""
    row = await _row_or_404(session, shop_id)
    now = await shops.find(session, row.kind, row.key)
    if now and now.variable:
        row.affiliate_id, row.wrapper_template = now.affiliate_id, now.wrapper_template
    row.enabled = body.enabled
    if now:
        _must_be_whole(replace(now, enabled=body.enabled))
    row.updated_by = admin.id
    row.updated_at = datetime.now(UTC)
    return await _fresh(session)


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
    return await _fresh(session)


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
    return await _fresh(session)


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
        sample=(
            f"“{book.title}” by {book.author}, ISBN {book.isbn13}"
            if body.kind == "bookseller"
            else f"the ingredient “{shops.SAMPLE_TERM}”"
        ),
    )
