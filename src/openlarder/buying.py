"""Buy links: where an edition of a book can be bought, through OpenLarder's
own /go/ address, which counts the click and sends the visitor on with the
affiliate ID (SCOPING.md, Tracking and disclosure).

Bookshop.org first (SCOPING.md, Revenue); Amazon waits for traffic. A link
is made from the edition's ISBN, so nothing is stored per edition, and only
once the affiliate ID is set: a link that earns nothing isn't shown. *Ray,
2026-11-09.* Only books have buy links; a family collection isn't for sale.
"""

import re
import uuid
from urllib.parse import urlsplit

from pydantic import BaseModel

from openlarder.config import get_settings

# Retailer key -> how pages name it.
RETAILERS = {"bookshop": "Bookshop.org"}

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


def destination(retailer: str, isbn13: str) -> str | None:
    """Where a click goes, with the affiliate ID; None while there's none."""
    affiliate = get_settings().bookshop_affiliate_id
    if retailer == "bookshop" and affiliate:
        return f"https://bookshop.org/a/{affiliate}/{isbn13}"
    return None


def links(edition_id: uuid.UUID, isbn13: str | None, source_kind: str) -> list[BuyLink]:
    if source_kind != "book" or not isbn13:
        return []
    return [
        BuyLink(retailer=key, label=label, url=f"/go/{key}/{edition_id}")
        for key, label in RETAILERS.items()
        if destination(key, isbn13)
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
