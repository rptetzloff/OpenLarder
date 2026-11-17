"""Shops: the booksellers, grocers and producers a link out of the site can
go to, read from their table (migration 0073), and how each one's address
is made.

*Decided by Ray, 2026-11-13* (round 4, part D): the affiliate settings were
environment variables, and the shops a list in code. Now a shop is a row an
administrator can change with no redeploy; buying.py and grocery.py ask
here.

**Read once a minute.** The rows are kept in the process for 60 seconds, so
a page doesn't ask the database for them every time and every worker has a
change within a minute. reset() forgets them at once, for whoever just
changed one and for tests.

**Builders.** A shop's builder says how its address is made from the row
and the book or the ingredient:

- `bookshop`: the shop's address with the affiliate id in it.
- `amazon`: for a book its ISBN-10 where it has one and a search where it
  doesn't; for an ingredient a search of Amazon Fresh; for a piece of
  equipment a search of all of Amazon; the Associates tag on each.
- `wrapped`: the shop's address inside an affiliate network's deep link.
- `template`: the shop's address alone.
- `direct`: the address as written, for a producer's referral link.

A shop's address is its product_template, with {isbn13}, {isbn10}, {title},
{author} and {words} (title and author, for a search) for a book, {term}
for an ingredient or a piece of equipment, and {id} for the affiliate id; each is encoded for an
address as it's put in. {words} isn't in Ray's list: Kobo is searched by
title and author, and without it that search stayed in code.

**A link that earns nothing isn't shown** (*Ray, 2026-11-09*): a bookseller
or a grocer is offered when it's switched on and its builder has what it
needs. A producer may earn nothing and still be listed (*Ray, 2026-11-13*):
it's offered when it's switched on and has its address (producers.py).

**The variables are gone.** For the one release after the table came, a
row nobody had changed that had no setting took it from the environment
variable it used to be in. Migration 0076 copied any such setting onto its
row, and nothing here reads the environment now: a shop is what its row
says. An OPENLARDER_AMAZON_TAG left behind does nothing.
"""

import time
import uuid
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, quote_plus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.models import Shop as ShopRow

Kind = Literal["bookseller", "grocer", "producer", "kitchen"]
# How long the rows are kept before they're read again.
TTL = 60.0


@dataclass(frozen=True)
class Book:
    """What a bookseller's address is made from."""

    isbn13: str
    title: str
    author: str | None


@dataclass(frozen=True)
class Shop:
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
    position: int
    # Producers only: what it is, what a new customer gets, and the US
    # states it ships to (None, everywhere).
    description: str | None = None
    offer: str | None = None
    ships_to: tuple[str, ...] | None = None
    # Its row's id; None for one being tried that has no row.
    id: uuid.UUID | None = None


# When they were read, and the rows.
_kept: tuple[float, list[Shop]] | None = None


def reset() -> None:
    """Forget the rows kept, so the next asking reads them again."""
    global _kept
    _kept = None


async def _rows(session: AsyncSession) -> list[Shop]:
    global _kept
    if _kept is None or time.monotonic() - _kept[0] > TTL:
        found = await session.scalars(select(ShopRow).order_by(ShopRow.kind, ShopRow.position))
        _kept = (
            time.monotonic(),
            [
                Shop(
                    key=r.key,
                    kind=r.kind,
                    label=r.label,
                    builder=r.builder,
                    affiliate_id=r.affiliate_id,
                    wrapper_template=r.wrapper_template,
                    product_template=r.product_template,
                    format=r.format,
                    earns=r.earns,
                    note=r.note,
                    enabled=r.enabled,
                    position=r.position,
                    description=r.description,
                    offer=r.offer,
                    ships_to=tuple(r.ships_to) if r.ships_to is not None else None,
                    id=r.id,
                )
                for r in found
            ],
        )
    return _kept[1]


async def listed(session: AsyncSession, kind: Kind) -> list[Shop]:
    """Every shop of a kind, in the order they're shown, switched on or not."""
    return [s for s in await _rows(session) if s.kind == kind]


async def find(session: AsyncSession, kind: Kind, key: str) -> Shop | None:
    return next((s for s in await listed(session, kind) if s.key == key), None)


# What a shop's own address may ask for, by the kind of shop.
PLACEHOLDERS = {
    "bookseller": ("isbn13", "isbn10", "title", "author", "words", "id"),
    "grocer": ("term", "id"),
    # A producer's address is its referral link, used as written.
    "producer": (),
    # A kitchen shop is searched for a piece of equipment as a grocer is
    # for an ingredient.
    "kitchen": ("term", "id"),
}
# The builders a kind of shop may have.
BUILDERS = {
    "bookseller": ("bookshop", "amazon", "wrapped", "template"),
    "grocer": ("amazon", "wrapped", "template"),
    "producer": ("direct",),
    "kitchen": ("amazon", "wrapped", "template"),
}
# What's shown for "Test link": a book and an ingredient that are no one's.
SAMPLE_BOOK = Book(isbn13="9780393541113", title="A Sample Cookbook", author="Ann Author")
SAMPLE_TERM = "olive oil"
SAMPLE_EQUIPMENT = "Dutch oven"


def lacks(shop: Shop) -> str | None:
    """What its builder still needs before a link can be made, in words to
    finish "It needs …"; None when it has all it needs."""
    if shop.builder == "amazon":
        return None if shop.affiliate_id else "its Associates tag"
    if shop.builder == "bookshop" and not shop.affiliate_id:
        return "its affiliate id"
    if shop.builder == "wrapped" and not shop.wrapper_template:
        return "the affiliate network's deep link"
    return None if shop.product_template else "the shop's own address"


def sample(shop: Shop) -> str | None:
    """Where a click would go for the sample book or ingredient."""
    if shop.kind == "bookseller":
        return for_book(shop, SAMPLE_BOOK)
    if shop.kind == "producer":
        return for_producer(shop)
    return for_term(shop, SAMPLE_EQUIPMENT if shop.kind == "kitchen" else SAMPLE_TERM)


def _filled(template: str, values: dict[str, str | None]) -> str | None:
    """The template with each {name} replaced; None if it asks for something
    there isn't (an ISBN-10 for a 979 book)."""
    out = template
    for name, value in values.items():
        if "{" + name + "}" in out:
            if value is None:
                return None
            out = out.replace("{" + name + "}", value)
    return out


def _wrapped(template: str, product: str) -> str:
    """A network's deep-link template with the shop's address put in."""
    return template.replace("{url}", quote(product, safe=""))


def isbn10(isbn13: str) -> str | None:
    """The 10-digit form of a 978 ISBN; 979 ones have none."""
    if not isbn13.startswith("978"):
        return None
    core = isbn13[3:12]
    check = (11 - sum((10 - i) * int(d) for i, d in enumerate(core)) % 11) % 11
    return core + ("X" if check == 10 else str(check))


def _address(shop: Shop, values: dict[str, str | None]) -> str | None:
    """Where the shop's builder sends a click, from its templates; None while
    it hasn't what it needs."""
    values = {**values, "id": quote(shop.affiliate_id, safe="") if shop.affiliate_id else None}
    product = _filled(shop.product_template, values) if shop.product_template else None
    if shop.builder == "direct":
        return shop.product_template
    if product is None:
        return None
    if shop.builder == "wrapped":
        return _wrapped(shop.wrapper_template, product) if shop.wrapper_template else None
    if shop.builder == "bookshop":
        return product if shop.affiliate_id else None
    return product if shop.builder == "template" else None


def for_book(shop: Shop, book: Book) -> str | None:
    """Where a click on a bookseller's link goes, for this book."""
    if shop.builder == "amazon":
        if not shop.affiliate_id:
            return None
        tag = quote(shop.affiliate_id, safe="")
        short = isbn10(book.isbn13)
        # Amazon files a print book under its ISBN-10; a 979 one is searched for.
        if short:
            return f"https://www.amazon.com/dp/{short}?tag={tag}"
        return f"https://www.amazon.com/s?k={book.isbn13}&i=stripbooks&tag={tag}"
    return _address(
        shop,
        {
            "isbn13": book.isbn13,
            "isbn10": isbn10(book.isbn13),
            "title": quote(book.title, safe=""),
            "author": quote(book.author, safe="") if book.author else "",
            "words": quote(" ".join(x for x in (book.title, book.author) if x)),
        },
    )


def for_term(shop: Shop, term: str) -> str | None:
    """Where a click on a grocer's link goes, for this ingredient, or on a
    kitchen shop's, for this piece of equipment."""
    if shop.builder == "amazon":
        if not shop.affiliate_id:
            return None
        tag = quote(shop.affiliate_id, safe="")
        # Groceries are Amazon Fresh's. Equipment is in no one department,
        # so its search names none.
        within = "&i=amazonfresh" if shop.kind == "grocer" else ""
        return f"https://www.amazon.com/s?k={quote_plus(term)}{within}&tag={tag}"
    return _address(shop, {"term": quote_plus(term)})


# As long as a name may be.
MAX_TERM = 200


def shopping_term(typed: str | None, name: str) -> str | None:
    """What a Shop link is to search for, as it's kept for an ingredient
    or a piece of equipment: its spaces tidied, and nothing when it's
    empty or only says the name again, since a link with no term searches
    for the name."""
    term = " ".join((typed or "").split())
    return term if term and term.casefold() != name.casefold() else None


def for_producer(shop: Shop) -> str | None:
    """Where a click on a producer's link goes: its address, as written."""
    return shop.product_template if shop.builder == "direct" else None
