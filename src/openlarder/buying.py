"""Buy links: where an edition of a book can be bought, through OpenLarder's
own /go/ address, which counts the click and sends the visitor on with the
affiliate ID (SCOPING.md, Tracking and disclosure).

The booksellers are rows of the shops table (shops.py), which an
administrator changes from the site (*Ray, 2026-11-13*; they were a list
here, each with its setting in an environment variable). A shop shows only
once it's switched on and has its affiliate setting: a link that earns
nothing isn't shown. *Ray, 2026-11-09.* Bookshop.org takes an affiliate ID
and Amazon an Associates tag, each put into the shop's own address. The
others are reached through affiliate networks (Rakuten, Impact and the
like), whose deep-link templates wrap any address at the shop: the setting
is that template with {url} where the address goes, so it works whichever
network a shop uses. Audiobook shops are left out: a cookbook is for the
kitchen. Only books with an ISBN have buy links; a family collection isn't
for sale.
"""

import re
import uuid
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import shops
from openlarder.shops import Book, isbn10

__all__ = [
    "Book",
    "BuyLink",
    "destination",
    "is_bot",
    "isbn10",
    "keys",
    "labels",
    "links",
    "page_of",
]

# Crawlers and link previews, which aren't people buying anything.
_BOT = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|embedly|curl|wget|python-|"
    r"httpx|go-http|java/|headless|lighthouse|monitor|uptime",
    re.IGNORECASE,
)
MAX_PAGE = 300


class BuyLink(BaseModel):
    retailer: str
    label: str
    # OpenLarder's own address, which counts the click.
    url: str
    note: str | None = None
    format: Literal["print", "ebook"] = "print"


async def destination(session: AsyncSession, retailer: str, book: Book) -> str | None:
    """Where a click goes, with the affiliate setting; None while the shop is
    switched off or has none."""
    shop = await shops.find(session, "bookseller", retailer)
    return shops.for_book(shop, book) if shop and shop.enabled else None


async def keys(session: AsyncSession) -> list[str]:
    """Every bookseller's key, switched on or not, in the order shown."""
    return [s.key for s in await shops.listed(session, "bookseller")]


async def labels(session: AsyncSession) -> dict[str, str]:
    return {s.key: s.label for s in await shops.listed(session, "bookseller")}


async def links(
    session: AsyncSession,
    edition_id: uuid.UUID,
    isbn13: str | None,
    source_kind: str,
    title: str = "",
    author: str | None = None,
) -> list[BuyLink]:
    if source_kind != "book" or not isbn13:
        return []
    book = Book(isbn13=isbn13, title=title, author=author)
    return [
        BuyLink(
            retailer=s.key,
            label=s.label,
            url=f"/go/{s.key}/{edition_id}",
            note=s.note,
            format="ebook" if s.format == "ebook" else "print",
        )
        for s in await shops.listed(session, "bookseller")
        if s.enabled and shops.for_book(s, book)
    ]


def is_bot(user_agent: str | None) -> bool:
    return not user_agent or bool(_BOT.search(user_agent))


def page_of(asked: str | None, referer: str | None) -> str | None:
    """The OpenLarder page the link was on: the path the page sent, or the
    referring page's path. A path only, never a query or another site."""
    for candidate in (asked, urlsplit(referer).path if referer else None):
        if candidate and candidate.startswith("/") and not candidate.startswith("//"):
            return urlsplit(candidate).path[:MAX_PAGE]
    return None
