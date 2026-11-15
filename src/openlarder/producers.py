"""Producers: farms, mills and makers that sell ingredients themselves,
linked from the ingredients they supply and from a page of their own.
*Decided by Ray, 2026-11-13* (round 4, part D4).

A producer is a row of the shops table (shops.py) of the kind "producer":
its address is its referral link, used as written. It's **offered** when
it's switched on and has that address. Unlike a bookseller or a grocer it
may earn OpenLarder nothing and still be listed.

**What it supplies** is a list of ingredients (producer_ingredients). A
broad one covers the ingredients under it: a producer that supplies "Beef"
is on Ground beef's page too. An ingredient's page shows at most two, in
the order an administrator put them in.

**What's said beside its link** is the producer's own note, which must say
plainly what is earned and by whom; one that earns nothing says so in the
site's words (NOTHING_EARNED).

**Where it ships** is said, and nobody's place is guessed: the card goes
to everyone (*Ray: version 1*).

**Only ingredients everyone can see.** A producer can't be given an
ingredient that only a private family collection uses, and one that
becomes so later isn't named on the Producers page: what's listed there is
read as someone signed out would see it. *Claude's choice, 2026-11-15*,
from the rule that a private collection shows to nobody.

A click goes through /go/producer/<key> (routers/go.py), which counts it
like the others: which producer, which page, when, and nothing about who.
"""

import uuid

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import shops, visibility
from openlarder.models import Ingredient, ProducerIngredient

# How many an ingredient's page shows.
ON_A_PAGE = 2
NOTHING_EARNED = "OpenLarder earns nothing from this link."

# What ships_to may hold: the states' postal codes, and the District's.
STATES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


class Named(BaseModel):
    id: uuid.UUID
    name: str


class ProducerCard(BaseModel):
    """A producer as an ingredient's page shows it."""

    key: str
    label: str
    description: str | None
    offer: str | None
    # "Ships to 30 states", or "Ships everywhere".
    ships: str
    # affiliate, referral or none: whether the link is a sponsored one.
    earns: str
    # What's said beside the link: what is earned, and by whom.
    disclosure: str
    # /go/producer/<key>, which counts the click and sends it on.
    url: str


class ProducerOut(ProducerCard):
    """And as the Producers page does: with what it supplies, and where it
    ships by name."""

    supplies: list[Named]
    # The states' names, in order; empty when it ships everywhere.
    states: list[str]


def ships(shop: shops.Shop) -> str:
    """Where it ships, in a few words. The District is counted with the
    states: "30 states" is what a reader wants, not "29 states and DC"."""
    if not shop.ships_to:
        return "Ships everywhere"
    n = len(shop.ships_to)
    if n == 1:
        return f"Ships to {STATES.get(shop.ships_to[0], shop.ships_to[0])} only"
    return f"Ships to {n} states"


def disclosure(shop: shops.Shop) -> str:
    return NOTHING_EARNED if shop.earns == "none" or not shop.note else shop.note


def _card(shop: shops.Shop) -> dict:
    return {
        "key": shop.key,
        "label": shop.label,
        "description": shop.description,
        "offer": shop.offer,
        "ships": ships(shop),
        "earns": shop.earns,
        "disclosure": disclosure(shop),
        "url": f"/go/producer/{shop.key}",
    }


async def offered(session: AsyncSession) -> list[shops.Shop]:
    """The producers switched on with their address, in order."""
    return [
        p for p in await shops.listed(session, "producer") if p.enabled and shops.for_producer(p)
    ]


async def any_offered(session: AsyncSession) -> bool:
    return bool(await offered(session))


async def destination(session: AsyncSession, key: str) -> str | None:
    """Where a click goes; None while the producer is switched off or has
    no address."""
    shop = await shops.find(session, "producer", key)
    return shops.for_producer(shop) if shop and shop.enabled else None


async def labels(session: AsyncSession) -> dict[str, str]:
    return {p.key: p.label for p in await shops.listed(session, "producer")}


async def listed(session: AsyncSession) -> list[ProducerOut]:
    """The Producers page: each one offered, with the ingredients it
    supplies that everyone can see, by name."""
    found = await offered(session)
    if not found:
        return []
    supplied: dict[uuid.UUID, list[Named]] = {}
    rows = await session.execute(
        select(ProducerIngredient.shop_id, Ingredient.id, Ingredient.name)
        .join(Ingredient, Ingredient.id == ProducerIngredient.ingredient_id)
        .where(
            ProducerIngredient.shop_id.in_([p.id for p in found]),
            visibility.ingredients_seen_by(None),
        )
        .order_by(Ingredient.name)
    )
    for shop_id, ingredient_id, name in rows:
        supplied.setdefault(shop_id, []).append(Named(id=ingredient_id, name=name))
    return [
        ProducerOut(
            **_card(p),
            supplies=supplied.get(p.id, []),
            states=sorted(STATES[code] for code in p.ships_to or () if code in STATES),
        )
        for p in found
    ]


def _with_broader(ingredient_id: uuid.UUID):
    """The ingredient and every broader one above it. UNION, not UNION ALL:
    a loop of parents, which the site refuses to make, would still end."""
    up = (
        select(Ingredient.id, Ingredient.parent_id)
        .where(Ingredient.id == ingredient_id)
        .cte("up", recursive=True)
    )
    return up.union(
        select(Ingredient.id, Ingredient.parent_id).where(Ingredient.id == up.c.parent_id)
    )


async def for_ingredient(session: AsyncSession, ingredient_id: uuid.UUID) -> list[ProducerCard]:
    """The producers that supply an ingredient, itself or through a broader
    one: the first ON_A_PAGE, in their order."""
    found = await offered(session)
    if not found:
        # Most pages, most of the time: no query at all.
        return []
    up = _with_broader(ingredient_id)
    theirs = set(
        await session.scalars(
            select(ProducerIngredient.shop_id).where(
                ProducerIngredient.ingredient_id.in_(select(up.c.id))
            )
        )
    )
    return [ProducerCard(**_card(p)) for p in found if p.id in theirs][:ON_A_PAGE]
