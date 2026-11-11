"""Buy links: where an edition of a book can be bought, through OpenLarder's
own /go/ address, which counts the click and sends the visitor on with the
affiliate ID (SCOPING.md, Tracking and disclosure).

Each shop shows only once its affiliate setting is in Coolify: a link that
earns nothing isn't shown. *Ray, 2026-11-09.* Bookshop.org takes an
affiliate ID and Amazon an Associates tag, each put into the shop's own
address. The others are reached through affiliate networks (Rakuten, Impact
and the like), whose deep-link templates wrap any address at the shop: the
setting is that template with {url} where the address goes, so it works
whichever network a shop uses. Audiobook shops are left out: a cookbook is
for the kitchen. Only books with an ISBN have buy links; a family
collection isn't for sale.
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urlsplit

from pydantic import BaseModel

from openlarder.config import Settings, get_settings

# Crawlers and link previews, which aren't people buying anything.
_BOT = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|embedly|curl|wget|python-|"
    r"httpx|go-http|java/|headless|lighthouse|monitor|uptime",
    re.IGNORECASE,
)
MAX_PAGE = 300


@dataclass(frozen=True)
class Book:
    """What a shop's address is made from."""

    isbn13: str
    title: str
    author: str | None


def isbn10(isbn13: str) -> str | None:
    """The 10-digit form of a 978 ISBN; 979 ones have none."""
    if not isbn13.startswith("978"):
        return None
    core = isbn13[3:12]
    check = (11 - sum((10 - i) * int(d) for i, d in enumerate(core)) % 11) % 11
    return core + ("X" if check == 10 else str(check))


def _wrapped(template: str | None, product: str) -> str | None:
    """A network's deep-link template with the shop's address put in."""
    return template.replace("{url}", quote(product, safe="")) if template else None


def _bookshop(s: Settings, b: Book) -> str | None:
    if not s.bookshop_affiliate_id:
        return None
    return f"https://bookshop.org/a/{s.bookshop_affiliate_id}/{b.isbn13}"


def _amazon(s: Settings, b: Book) -> str | None:
    if not s.amazon_tag:
        return None
    short = isbn10(b.isbn13)
    # Amazon files a print book under its ISBN-10; a 979 one is searched for.
    if short:
        return f"https://www.amazon.com/dp/{short}?tag={s.amazon_tag}"
    return f"https://www.amazon.com/s?k={b.isbn13}&i=stripbooks&tag={s.amazon_tag}"


def _kobo_search(b: Book) -> str:
    # An ebook has its own ISBN, so Kobo is searched by title and author.
    words = " ".join(x for x in (b.title, b.author) if x)
    return f"https://www.kobo.com/us/en/search?query={quote(words)}"


@dataclass(frozen=True)
class Retailer:
    key: str
    label: str
    destination: Callable[[Settings, Book], str | None]
    # What the shop's programme asks to be said beside its link, if anything.
    note: str | None = None
    # What it sells the book as: the buy box labels each button with it.
    format: Literal["print", "ebook"] = "print"


# In the order pages show them: the independent bookshops' first.
RETAILERS = [
    Retailer("bookshop", "Bookshop.org", _bookshop),
    Retailer(
        "bn",
        "Barnes & Noble",
        lambda s, b: _wrapped(
            s.barnes_noble_link, f"https://www.barnesandnoble.com/w/?ean={b.isbn13}"
        ),
    ),
    Retailer(
        "thriftbooks",
        "ThriftBooks",
        lambda s, b: _wrapped(
            s.thriftbooks_link, f"https://www.thriftbooks.com/browse/?b.search={b.isbn13}"
        ),
    ),
    Retailer(
        "bookoutlet",
        "Book Outlet",
        lambda s, b: _wrapped(s.bookoutlet_link, f"https://bookoutlet.com/search?q={b.isbn13}"),
    ),
    Retailer(
        "amazon",
        "Amazon",
        _amazon,
        note="As an Amazon Associate, OpenLarder earns from qualifying purchases.",
    ),
    Retailer(
        "kobo",
        "Kobo",
        lambda s, b: _wrapped(s.kobo_link, _kobo_search(b)),
        format="ebook",
    ),
]
BY_KEY = {r.key: r for r in RETAILERS}


class BuyLink(BaseModel):
    retailer: str
    label: str
    # OpenLarder's own address, which counts the click.
    url: str
    note: str | None = None
    format: Literal["print", "ebook"] = "print"


def destination(retailer: str, book: Book) -> str | None:
    """Where a click goes, with the affiliate setting; None while there's none."""
    found = BY_KEY.get(retailer)
    return found.destination(get_settings(), book) if found else None


def links(
    edition_id: uuid.UUID,
    isbn13: str | None,
    source_kind: str,
    title: str = "",
    author: str | None = None,
) -> list[BuyLink]:
    if source_kind != "book" or not isbn13:
        return []
    book = Book(isbn13=isbn13, title=title, author=author)
    settings = get_settings()
    return [
        BuyLink(
            retailer=r.key,
            label=r.label,
            url=f"/go/{r.key}/{edition_id}",
            note=r.note,
            format=r.format,
        )
        for r in RETAILERS
        if r.destination(settings, book)
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
