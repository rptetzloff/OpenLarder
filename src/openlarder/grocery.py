"""Grocery links: where to buy an ingredient, through OpenLarder's own
/go/grocer/ address, which counts the click and sends the visitor on with
the affiliate ID, the same way as the book shops' links (buying.py).

*Ray, 2026-11-11:* Instacart first; anyone may choose another grocer, as
Instacart may have nothing near them. The grocers are rows of the shops
table (shops.py; *Ray, 2026-11-13*), and each shows only once it's switched
on with its affiliate setting. A link is a search at the grocer for the
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
changed on the shop.
"""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import shops


class GrocerOut(BaseModel):
    key: str
    label: str
    note: str | None = None


async def offered(session: AsyncSession) -> list[GrocerOut]:
    """The grocers switched on with their affiliate setting in place, in order."""
    return [
        GrocerOut(key=g.key, label=g.label, note=g.note)
        for g in await shops.listed(session, "grocer")
        if g.enabled and shops.for_term(g, "onion")
    ]


async def keys(session: AsyncSession) -> list[str]:
    """Every grocer's key, switched on or not."""
    return [g.key for g in await shops.listed(session, "grocer")]


async def labels(session: AsyncSession) -> dict[str, str]:
    return {g.key: g.label for g in await shops.listed(session, "grocer")}


async def destination(session: AsyncSession, grocer: str, term: str) -> str | None:
    """Where a click goes; None while the grocer is switched off or has no
    setting."""
    shop = await shops.find(session, "grocer", grocer)
    return shops.for_term(shop, term) if shop and shop.enabled else None
