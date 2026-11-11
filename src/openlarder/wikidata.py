"""Facts about authors from Wikidata: born and died, country, website.

Wikidata is CC0, so its facts can sit in the ODbL catalog; Wikipedia's prose
can't (SCOPING.md, Authors). One query to Wikidata's query service answers
for a batch of authors, found by their Open Library ID (Wikidata's P648) or
by a Wikidata ID an admin gave, and asks only for the four facts: an item's
whole record runs to megabytes.
"""

import asyncio
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any

import httpx2
from fastapi import Depends

from openlarder.openlibrary import USER_AGENT

ENDPOINT = "https://query.wikidata.org/sparql"
TIMEOUT = 60.0
# Batches are asked for one after another, a second apart at least: the
# query service asks callers to keep to one query at a time. Tests set it
# to 0.
MIN_INTERVAL = 1.0
_pace = asyncio.Lock()
_last = 0.0

_OL = re.compile(r"^OL[1-9][0-9]*A$")
_Q = re.compile(r"^Q[1-9][0-9]*$")
# A year at the start of an xsd:dateTime, BC ones negative.
_YEAR = re.compile(r"^(-?[0-9]{1,4})-")


def wikidata_transport() -> httpx2.AsyncBaseTransport | None:
    """A dependency: None means the real Wikidata; tests replace this with a fake."""
    return None


WikidataTransport = Annotated[httpx2.AsyncBaseTransport | None, Depends(wikidata_transport)]


class Unavailable(RuntimeError):
    pass


class BadReference(ValueError):
    pass


@dataclass
class Facts:
    wikidata_id: str
    open_library_ids: set[str] = field(default_factory=set)
    born_year: int | None = None
    died_year: int | None = None
    country: str | None = None
    website: str | None = None


def item_url(wikidata_id: str) -> str:
    return f"https://www.wikidata.org/wiki/{wikidata_id}"


def parse_reference(raw: str) -> str:
    """A Wikidata ID ("Q214477") from itself or a link to its page."""
    found = re.search(r"(?<![A-Za-z0-9])Q[1-9][0-9]*(?![0-9])", raw.strip())
    if not found:
        raise BadReference("Give a Wikidata ID, like Q214477, or a link to the item.")
    return found.group(0)


def _query(selector: str) -> str:
    # P569 born, P571 founded (an organisation); P570 died; P27 citizenship,
    # P17 an organisation's country; P856 official website.
    return f"""SELECT ?item ?ol ?born ?died ?countryLabel ?website WHERE {{
  {selector}
  OPTIONAL {{ ?item wdt:P569|wdt:P571 ?born }}
  OPTIONAL {{ ?item wdt:P570 ?died }}
  OPTIONAL {{ ?item wdt:P27|wdt:P17 ?country }}
  OPTIONAL {{ ?item wdt:P856 ?website }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def _value(row: dict[str, Any], name: str) -> str | None:
    cell = row.get(name)
    # An unknown value comes as a blank node, not a literal.
    return cell["value"] if cell and cell.get("type") in ("literal", "uri") else None


def _year(value: str | None) -> int | None:
    found = _YEAR.match(value or "")
    return int(found.group(1)) if found else None


def _read(rows: list[dict[str, Any]]) -> dict[str, Facts]:
    """Rows to facts by Wikidata ID: a row per combination of values, so an
    item with two countries and two websites comes as four."""
    found: dict[str, Facts] = {}
    countries: dict[str, list[str]] = {}
    sites: dict[str, list[str]] = {}
    for row in rows:
        item = (_value(row, "item") or "").rsplit("/", 1)[-1]
        if not _Q.match(item):
            continue
        facts = found.setdefault(item, Facts(item))
        if ol := _value(row, "ol"):
            facts.open_library_ids.add(ol)
        born, died = _year(_value(row, "born")), _year(_value(row, "died"))
        # The earliest, when sources disagree.
        if born is not None and (facts.born_year is None or born < facts.born_year):
            facts.born_year = born
        if died is not None and (facts.died_year is None or died < facts.died_year):
            facts.died_year = died
        country = _value(row, "countryLabel")
        # An item with no English label is labelled with its own ID.
        if country and not _Q.match(country) and country not in countries.setdefault(item, []):
            countries[item].append(country)
        site = _value(row, "website")
        if (
            site
            and site.startswith(("https://", "http://"))
            and site not in sites.setdefault(item, [])
        ):
            sites[item].append(site)
    for item, facts in found.items():
        facts.country = " and ".join(sorted(countries.get(item, []))[:2]) or None
        # https first, then the shortest: usually the site's front page.
        ranked = sorted(sites.get(item, []), key=lambda s: (not s.startswith("https"), len(s)))
        facts.website = ranked[0] if ranked else None
    return found


async def _wait_turn() -> None:
    global _last
    async with _pace:
        delay = _last + MIN_INTERVAL - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        _last = time.monotonic()


async def _ask(client: httpx2.AsyncClient, query: str) -> list[dict[str, Any]]:
    await _wait_turn()
    try:
        response = await client.post(
            ENDPOINT,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
    except httpx2.HTTPError as exc:
        raise Unavailable(f"Wikidata could not be reached: {exc!r}") from exc
    if response.status_code >= 400:
        raise Unavailable(f"Wikidata answered {response.status_code}")
    return response.json()["results"]["bindings"]


async def lookup(
    open_library_ids: Sequence[str] = (),
    wikidata_ids: Sequence[str] = (),
    transport: httpx2.AsyncBaseTransport | None = None,
) -> dict[str, Facts]:
    """Facts for the items with these Open Library author IDs, or these
    Wikidata IDs, by Wikidata ID. Malformed IDs are left out rather than
    put in the query."""
    ols = sorted({i for i in open_library_ids if _OL.match(i)})
    qs = sorted({i for i in wikidata_ids if _Q.match(i)})
    rows: list[dict[str, Any]] = []
    async with httpx2.AsyncClient(
        transport=transport, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
    ) as client:
        if ols:
            values = " ".join(f'"{i}"' for i in ols)
            rows += await _ask(client, _query(f"VALUES ?ol {{ {values} }} ?item wdt:P648 ?ol ."))
        if qs:
            values = " ".join(f"wd:{i}" for i in qs)
            # schema:version, which every item has: without it, VALUES
            # answers for an ID with no item behind it too.
            selector = (
                f"VALUES ?item {{ {values} }} ?item schema:version [] ."
                " OPTIONAL { ?item wdt:P648 ?ol }"
            )
            rows += await _ask(client, _query(selector))
    return _read(rows)


@dataclass
class Label:
    wikidata_id: str
    label: str | None
    description: str | None


async def labels(
    wikidata_ids: Sequence[str], transport: httpx2.AsyncBaseTransport | None = None
) -> dict[str, Label]:
    """The English label and description of each item that exists, by ID:
    what an ingredient is linked to, shown to check it's the right thing."""
    qs = sorted({i for i in wikidata_ids if _Q.match(i)})
    if not qs:
        return {}
    values = " ".join(f"wd:{i}" for i in qs)
    query = f"""SELECT ?item ?label ?description WHERE {{
  VALUES ?item {{ {values} }} ?item schema:version [] .
  OPTIONAL {{ ?item rdfs:label ?label FILTER(LANG(?label) = "en") }}
  OPTIONAL {{ ?item schema:description ?description FILTER(LANG(?description) = "en") }}
}}"""
    async with httpx2.AsyncClient(
        transport=transport, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
    ) as client:
        rows = await _ask(client, query)
    found: dict[str, Label] = {}
    for row in rows:
        item = (_value(row, "item") or "").rsplit("/", 1)[-1]
        if _Q.match(item):
            found.setdefault(item, Label(item, _value(row, "label"), _value(row, "description")))
    return found


async def by_ndb(transport: httpx2.AsyncBaseTransport | None = None) -> dict[int, Label]:
    """Every item citing a USDA NDB number (P1978), by the number: some
    1,500, in one query. Where several cite one, one with an English label,
    the oldest first."""
    query = """SELECT ?item ?ndb ?label WHERE {
  ?item wdt:P1978 ?ndb .
  OPTIONAL { ?item rdfs:label ?label FILTER(LANG(?label) = "en") }
}"""
    async with httpx2.AsyncClient(
        transport=transport, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
    ) as client:
        rows = await _ask(client, query)
    found: dict[int, Label] = {}

    def preferred(row: dict[str, Any]) -> tuple[bool, int]:
        # One with an English label, then the oldest (the lowest number).
        number = re.sub(r"\D", "", (_value(row, "item") or "").rsplit("/", 1)[-1])
        return (_value(row, "label") is None, int(number or 0))

    for row in sorted(rows, key=preferred):
        item = (_value(row, "item") or "").rsplit("/", 1)[-1]
        try:
            ndb = int(_value(row, "ndb") or "")
        except ValueError:
            continue
        if _Q.match(item):
            found.setdefault(ndb, Label(item, _value(row, "label"), None))
    return found


@dataclass
class Names:
    wikidata_id: str
    label: str | None = None
    # Other English names, as Wikidata has them.
    aliases: set[str] = field(default_factory=set)
    # The British English label, where there is one.
    uk: str | None = None
    # What it's a subclass of (P279).
    parents: set[str] = field(default_factory=set)


async def names(
    wikidata_ids: Sequence[str], transport: httpx2.AsyncBaseTransport | None = None
) -> dict[str, Names]:
    """Each item's other names and what it's a kind of, 200 to a query."""
    qs = sorted({i for i in wikidata_ids if _Q.match(i)})
    found: dict[str, Names] = {}
    async with httpx2.AsyncClient(
        transport=transport, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
    ) as client:
        for start in range(0, len(qs), 200):
            values = " ".join(f"wd:{i}" for i in qs[start : start + 200])
            query = f"""SELECT ?item ?label ?alias ?uk ?parent WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item rdfs:label ?label FILTER(LANG(?label) = "en") }}
  {{ ?item skos:altLabel ?alias FILTER(LANG(?alias) = "en") }}
  UNION {{ ?item rdfs:label ?uk FILTER(LANG(?uk) = "en-gb") }}
  UNION {{ ?item wdt:P279 ?parent }}
}}"""
            for row in await _ask(client, query):
                item = (_value(row, "item") or "").rsplit("/", 1)[-1]
                if not _Q.match(item):
                    continue
                n = found.setdefault(item, Names(item))
                n.label = n.label or _value(row, "label")
                if alias := _value(row, "alias"):
                    n.aliases.add(alias)
                if uk := _value(row, "uk"):
                    n.uk = uk
                parent = (_value(row, "parent") or "").rsplit("/", 1)[-1]
                if _Q.match(parent):
                    n.parents.add(parent)
    return found
