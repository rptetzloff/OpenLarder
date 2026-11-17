"""Equipment's shop links: where to buy a piece of equipment, through
OpenLarder's own /go/equipment/ address, which counts the click and sends
the visitor on with the affiliate ID, as an ingredient's grocery link does
(grocery.py), and this is that module over again.

*Ray's equipment spec, 2026-11-15, Part 8.* The shops are rows of the shops
table of kind `kitchen` (shops.py), and each shows only once it's switched
on with its affiliate setting. A link is a search at the shop for the thing
(its shopping term, or its name).

- **Amazon:** the Associates tag, in a search of all of Amazon. A grocer's
  Amazon link searches Amazon Fresh; this one names no department, since
  equipment is sold in several, and a department's name in the address is
  Amazon's to change.

Only Amazon is seeded (migration 0086), switched off. Another is added on
the Shops page with its own address, {term} where the thing's name goes.
"""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import shops

KIND = "kitchen"


class KitchenShopOut(BaseModel):
    key: str
    label: str
    note: str | None = None


async def offered(session: AsyncSession) -> list[KitchenShopOut]:
    """The shops switched on with their affiliate setting in place, in order."""
    return [
        KitchenShopOut(key=s.key, label=s.label, note=s.note)
        for s in await shops.listed(session, KIND)
        if s.enabled and shops.for_term(s, shops.SAMPLE_EQUIPMENT)
    ]


async def keys(session: AsyncSession) -> list[str]:
    """Every kitchen shop's key, switched on or not."""
    return [s.key for s in await shops.listed(session, KIND)]


async def labels(session: AsyncSession) -> dict[str, str]:
    return {s.key: s.label for s in await shops.listed(session, KIND)}


async def destination(session: AsyncSession, shop_key: str, term: str) -> str | None:
    """Where a click goes; None while the shop is switched off or has no
    setting."""
    shop = await shops.find(session, KIND, shop_key)
    return shops.for_term(shop, term) if shop and shop.enabled else None
