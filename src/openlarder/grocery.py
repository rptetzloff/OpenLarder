"""Grocery links: where to buy an ingredient, through OpenLarder's own
/go/grocer/ address, which counts the click and sends the visitor on with
the affiliate ID, the same way as the book shops' links (buying.py).

*Ray, 2026-11-11:* Instacart first; anyone may choose another grocer, as
Instacart may have nothing near them. Each grocer shows only once its
affiliate setting is in Coolify. A link is a search at the grocer for the
ingredient (its shopping term, or its name), and the visitor picks their
store there: Instacart's Developer Platform, which fills a cart with a
whole recipe's ingredients, takes no new applications (November 2026).

- **Instacart:** its affiliate programme on Impact; the setting is the
  deep-link template, with {url} where the address goes. Its terms say no
  grocery brand or store names or logos, so the links are words.
- **Amazon Fresh:** the Amazon Associates tag the book links use.
- **Walmart:** its affiliate programme's deep-link template, like
  Instacart's.

The search addresses are the grocers' own, as their sites use them; none
documents them, so a grocer changing one breaks its links until it's
changed here.
"""

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote_plus

from pydantic import BaseModel

from openlarder.buying import _wrapped
from openlarder.config import Settings, get_settings


@dataclass(frozen=True)
class Grocer:
    key: str
    label: str
    destination: Callable[[Settings, str], str | None]
    # What the grocer's programme asks to be said beside its link.
    note: str | None = None


def _amazon(s: Settings, term: str) -> str | None:
    if not s.amazon_tag:
        return None
    return f"https://www.amazon.com/s?k={quote_plus(term)}&i=amazonfresh&tag={s.amazon_tag}"


# In the order they're offered: Instacart first (Ray, 2026-11-11).
GROCERS = [
    Grocer(
        "instacart",
        "Instacart",
        lambda s, t: _wrapped(
            s.instacart_link, f"https://www.instacart.com/store/s?k={quote_plus(t)}"
        ),
    ),
    Grocer(
        "amazon",
        "Amazon Fresh",
        _amazon,
        note="As an Amazon Associate, OpenLarder earns from qualifying purchases.",
    ),
    Grocer(
        "walmart",
        "Walmart",
        lambda s, t: _wrapped(s.walmart_link, f"https://www.walmart.com/search?q={quote_plus(t)}"),
    ),
]
BY_KEY = {g.key: g for g in GROCERS}


class GrocerOut(BaseModel):
    key: str
    label: str
    note: str | None = None


def offered() -> list[GrocerOut]:
    """The grocers whose affiliate setting is in place, in order."""
    settings = get_settings()
    return [
        GrocerOut(key=g.key, label=g.label, note=g.note)
        for g in GROCERS
        if g.destination(settings, "onion")
    ]


def destination(grocer: str, term: str) -> str | None:
    """Where a click goes; None while the grocer has no setting."""
    found = BY_KEY.get(grocer)
    return found.destination(get_settings(), term) if found else None
