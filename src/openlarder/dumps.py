"""Weekly ODbL data dumps: the public catalog as files anyone may take.
*Ray, 2026-11-10: object storage (S3/R2); CSV and JSON Lines.* SCOPING.md:
the catalog is open data under the ODbL; dumps let the API's anonymous
limits stay low, since whoever wants everything takes the file.

What's in them is what someone signed out sees (visibility.py with no
viewer): no private family collection, nothing waiting for review, and no
ingredient or author only those use. Nothing about accounts: no user ids,
no who-added-what, no edit history.

Two zips a week, each with a README giving the licence and attribution:
one CSV per table, and the same catalog as JSON Lines with each recipe's
places and ingredients inside it. They're uploaded under dumps/ with the
date, and recorded in the dumps table, which /data lists. A dump older than
OPENLARDER_DUMPS_KEEP_DAYS (a year unless set) is deleted from both.
"""

import asyncio
import csv
import io
import json
import logging
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

from sqlalchemy import Table, and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from openlarder import s3, visibility
from openlarder.config import Settings, get_settings
from openlarder.models import (
    Author,
    Base,
    Dump,
    Ingredient,
    Recipe,
    Source,
)

log = logging.getLogger(__name__)
EVERY = timedelta(days=7)
LICENCE_URL = "https://opendatacommons.org/licenses/odbl/1-0/"
ATTRIBUTION = (
    "Contains information from OpenLarder (https://openlarder.com), "
    "which is made available under the Open Database License (ODbL)."
)

# Table -> the columns a dump keeps, in order.
COLUMNS = {
    "sources": [
        "id", "kind", "title", "subtitle", "host", "paywalled", "open_library_work_id",
    ],
    "editions": [
        "id", "source_id", "title", "isbn13", "publisher", "published_year",
        "open_library_edition_id",
    ],
    "issues": ["id", "source_id", "label", "published_on"],
    "episodes": ["id", "source_id", "season", "number", "title", "url", "aired_on"],
    "web_pages": ["id", "source_id", "url", "archive_url", "archived_at", "gone"],
    "authors": [
        "id", "name", "kind", "open_library_author_id", "wikidata_id", "born_year",
        "died_year", "country", "website",
    ],
    "author_links": ["id", "author_id", "url", "label"],
    "source_credits": ["source_id", "author_id", "position", "role", "credited_as"],
    "recipes": ["id", "source_id", "title", "chapter", "online_url"],
    "recipe_locations": [
        "recipe_id", "source_id", "edition_id", "page", "web_page_id", "issue_id",
        "episode_id", "at_seconds",
    ],
    "recipe_ingredients": ["id", "recipe_id", "position", "original_text"],
    "ingredient_options": [
        "recipe_ingredient_id", "recipe_id", "rank", "name", "ingredient_id", "sub_recipe_id",
    ],
    "ingredients": ["id", "name", "shopping_term", "parent_id", "fdc_id", "wikidata_id"],
    "ingredient_aliases": ["id", "ingredient_id", "name", "region"],
    "tags": ["id", "kind", "name"],
    "source_tags": ["source_id", "tag_id"],
    "recipe_tags": ["recipe_id", "tag_id"],
    "substitutions": [
        "id", "from_ingredient_id", "from_recipe_id", "to_ingredient_id", "to_recipe_id",
        "diet_tag_id", "diet_kind", "source_edition_id", "source_page", "note",
    ],
}  # fmt: skip

# The order rows come in: a recipe's lines and a line's options as written,
# a source's credits as printed; the rest by id.
ORDER = {
    "source_credits": ["source_id", "position"],
    "recipe_locations": ["recipe_id", "edition_id"],
    "recipe_ingredients": ["recipe_id", "position"],
    "ingredient_options": ["recipe_ingredient_id", "rank"],
    "source_tags": ["source_id", "tag_id"],
    "recipe_tags": ["recipe_id", "tag_id"],
}

ABOUT = {
    "sources": "Cookbooks, websites, magazines, shows and the rest; kind says which.",
    "editions": "A book's printings, by ISBN.",
    "issues": "A magazine's or newspaper's issues.",
    "episodes": "A show's, podcast's or video channel's episodes.",
    "web_pages": "Pages of websites and social media accounts, with the Internet Archive's copy.",
    "authors": "People and organisations credited on sources.",
    "author_links": "Authors' own sites and pages.",
    "source_credits": "Who each source credits, in order, as it prints them.",
    "recipes": "Recipes: their titles, and the source and chapter they're in.",
    "recipe_locations": "Where each recipe is: an edition's page, a web page, an issue, a show.",
    "recipe_ingredients": "Each recipe's ingredient lines as written, in order; no amounts.",
    "ingredient_options": "Each line read into its options, matched to an ingredient or a recipe.",
    "ingredients": (
        "Canonical ingredients, the broader one each is under, and the same food's"
        " USDA FoodData Central ID and Wikidata item, where linked."
    ),
    "ingredient_aliases": "Other names for ingredients.",
    "tags": "Course, cuisine, diet and technique tags.",
    "source_tags": "Tags on whole sources, which their recipes have too.",
    "recipe_tags": "Tags on recipes.",
    "substitutions": "What can stand in for what, and for which diet.",
}


def _seen() -> dict:
    """Each table's rows someone signed out sees."""
    sources = select(Source.id).where(visibility.sources_seen_by(None))
    recipes = select(Recipe.id).where(visibility.recipes_seen_by(None))
    ingredients = select(Ingredient.id).where(visibility.ingredients_seen_by(None))
    credited = select(Base.metadata.tables["source_credits"].c.author_id).where(
        Base.metadata.tables["source_credits"].c.source_id.in_(sources)
    )
    authors = select(Author.id).where(visibility.authors_seen_by(None), Author.id.in_(credited))
    t = Base.metadata.tables

    def by(table: str, column: str, ids):
        return t[table].c[column].in_(ids)

    subs = t["substitutions"].c
    return {
        "sources": by("sources", "id", sources),
        "editions": by("editions", "source_id", sources),
        "issues": by("issues", "source_id", sources),
        "episodes": by("episodes", "source_id", sources),
        "web_pages": by("web_pages", "source_id", sources),
        "authors": by("authors", "id", authors),
        "author_links": by("author_links", "author_id", authors),
        "source_credits": by("source_credits", "source_id", sources),
        "recipes": by("recipes", "id", recipes),
        "recipe_locations": by("recipe_locations", "recipe_id", recipes),
        "recipe_ingredients": by("recipe_ingredients", "recipe_id", recipes),
        "ingredient_options": by("ingredient_options", "recipe_id", recipes),
        "ingredients": by("ingredients", "id", ingredients),
        "ingredient_aliases": by("ingredient_aliases", "ingredient_id", ingredients),
        "tags": text("true"),
        "source_tags": by("source_tags", "source_id", sources),
        "recipe_tags": by("recipe_tags", "recipe_id", recipes),
        "substitutions": and_(
            or_(subs.from_ingredient_id.is_(None), subs.from_ingredient_id.in_(ingredients)),
            or_(subs.to_ingredient_id.is_(None), subs.to_ingredient_id.in_(ingredients)),
            or_(subs.from_recipe_id.is_(None), subs.from_recipe_id.in_(recipes)),
            or_(subs.to_recipe_id.is_(None), subs.to_recipe_id.in_(recipes)),
        ),
    }


def _plain(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


async def read(session: AsyncSession) -> dict[str, list[dict]]:
    """Every table's public rows, as plain values."""
    seen = _seen()
    rows: dict[str, list[dict]] = {}
    for name, columns in COLUMNS.items():
        table: Table = Base.metadata.tables[name]
        order = [table.c[c] for c in ORDER.get(name, COLUMNS[name][:1])]
        result = await session.execute(
            select(*(table.c[c] for c in columns)).where(seen[name]).order_by(*order)
        )
        rows[name] = [{c: _plain(v) for c, v in zip(columns, r, strict=True)} for r in result]
    # Links to what isn't in the dump are left blank: a sub-recipe that's
    # hidden, a broader ingredient only hidden recipes use.
    recipe_ids = {r["id"] for r in rows["recipes"]}
    ingredient_ids = {r["id"] for r in rows["ingredients"]}
    for option in rows["ingredient_options"]:
        if option["sub_recipe_id"] and option["sub_recipe_id"] not in recipe_ids:
            option["sub_recipe_id"] = None
        if option["ingredient_id"] and option["ingredient_id"] not in ingredient_ids:
            option["ingredient_id"] = None
    for ingredient in rows["ingredients"]:
        if ingredient["parent_id"] and ingredient["parent_id"] not in ingredient_ids:
            ingredient["parent_id"] = None
    return rows


def readme(day: str, rows: dict[str, list[dict]], kind: str) -> str:
    lines = [
        f"OpenLarder data dump, {day}",
        "",
        "OpenLarder (https://openlarder.com) is an open index of where recipes are",
        "(which cookbook, magazine, website or show, which page) and what goes in",
        "them, by name. It never holds amounts, methods or a book's text.",
        "",
        "LICENCE",
        "",
        "This database is made available under the Open Database License (ODbL) 1.0:",
        LICENCE_URL,
        "You may copy, share and adapt it, and build on it, if you credit",
        "OpenLarder and keep any database you make from it open under the same",
        "licence. Credit it like this:",
        "",
        f"  {ATTRIBUTION}",
        "",
        "Book details come from Open Library and author facts from Wikidata, both",
        "public domain (CC0). Private family collections, anything waiting for",
        "review, and everything about accounts are left out.",
        "",
        "WHAT'S IN IT",
        "",
    ]
    if kind == "csv":
        lines.append("One CSV per table, UTF-8, with a header row. Ids are UUIDs.")
    else:
        lines.append(
            "JSON Lines, one record a line: sources.jsonl (with their credits and"
            " editions), recipes.jsonl (with their places, ingredient lines and tags),"
            " ingredients.jsonl (with other names), authors.jsonl, tags.jsonl."
        )
    lines.append("")
    for name in COLUMNS:
        lines.append(f"{name}: {len(rows[name]):,} rows. {ABOUT[name]}")
    return "\n".join(lines) + "\n"


def _zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def csv_zip(day: str, rows: dict[str, list[dict]]) -> bytes:
    files = {"README.txt": readme(day, rows, "csv")}
    for name, columns in COLUMNS.items():
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows[name])
        files[f"{name}.csv"] = out.getvalue()
    return _zip(files)


def _jsonl(records) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def _group(rows: list[dict], key: str) -> dict:
    out: dict = {}
    for row in rows:
        out.setdefault(row[key], []).append({k: v for k, v in row.items() if k != key})
    return out


def json_zip(day: str, rows: dict[str, list[dict]]) -> bytes:
    credits = _group(rows["source_credits"], "source_id")
    editions = _group(rows["editions"], "source_id")
    tags_of_source = _group(rows["source_tags"], "source_id")
    places = _group(rows["recipe_locations"], "recipe_id")
    lines = _group(rows["recipe_ingredients"], "recipe_id")
    options = _group(rows["ingredient_options"], "recipe_ingredient_id")
    tags_of_recipe = _group(rows["recipe_tags"], "recipe_id")
    aliases = _group(rows["ingredient_aliases"], "ingredient_id")
    links = _group(rows["author_links"], "author_id")
    sources = [
        {
            **s,
            "credits": credits.get(s["id"], []),
            "editions": editions.get(s["id"], []),
            "tags": [t["tag_id"] for t in tags_of_source.get(s["id"], [])],
        }
        for s in rows["sources"]
    ]
    recipes = [
        {
            **r,
            "places": [
                {k: v for k, v in p.items() if k != "source_id"} for p in places.get(r["id"], [])
            ],
            "ingredients": [
                {
                    "text": line["original_text"],
                    "options": [
                        {k: v for k, v in o.items() if k != "recipe_id"}
                        for o in options.get(line["id"], [])
                    ],
                }
                for line in lines.get(r["id"], [])
            ],
            "tags": [t["tag_id"] for t in tags_of_recipe.get(r["id"], [])],
        }
        for r in rows["recipes"]
    ]
    ingredients = [{**i, "aliases": aliases.get(i["id"], [])} for i in rows["ingredients"]]
    authors = [{**a, "links": links.get(a["id"], [])} for a in rows["authors"]]
    return _zip(
        {
            "README.txt": readme(day, rows, "json"),
            "sources.jsonl": _jsonl(sources),
            "recipes.jsonl": _jsonl(recipes),
            "ingredients.jsonl": _jsonl(ingredients),
            "authors.jsonl": _jsonl(authors),
            "tags.jsonl": _jsonl(rows["tags"]),
            "substitutions.jsonl": _jsonl(rows["substitutions"]),
        }
    )


def public_url(settings: Settings, key: str) -> str:
    return f"{settings.dumps_public_url.rstrip('/')}/{key}"


async def build(
    session: AsyncSession,
    settings: Settings,
    built_by: uuid.UUID | None = None,
    transport=None,
) -> Dump:
    """Build both files, upload them, and record the dump."""
    if not settings.dumps_configured:
        raise RuntimeError("Data dumps aren't configured.")
    rows = await read(session)
    now = datetime.now(UTC)
    day = now.date().isoformat()
    stamp = now.strftime("%Y-%m-%dT%H%MZ")
    csv_bytes, json_bytes = csv_zip(day, rows), json_zip(day, rows)
    keys = (f"dumps/openlarder-{stamp}-csv.zip", f"dumps/openlarder-{stamp}-jsonl.zip")
    for key, body in zip(keys, (csv_bytes, json_bytes), strict=True):
        await s3.put(
            settings.dumps_endpoint,
            settings.dumps_bucket,
            key,
            body,
            "application/zip",
            settings.dumps_access_key,
            settings.dumps_secret_key,
            settings.dumps_region,
            transport,
        )
    dump = Dump(
        csv_key=keys[0],
        csv_bytes=len(csv_bytes),
        json_key=keys[1],
        json_bytes=len(json_bytes),
        counts={name: len(rows[name]) for name in COLUMNS},
        built_by=built_by,
    )
    session.add(dump)
    await session.commit()
    await session.refresh(dump)
    log.info("Built data dump %s: %s recipes", stamp, len(rows["recipes"]))
    return dump


async def prune(session: AsyncSession, settings: Settings, transport=None) -> int:
    """Delete dumps older than OPENLARDER_DUMPS_KEEP_DAYS from the bucket and
    the list; the newest is always kept. How many went."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.dumps_keep_days)
    newest = await session.scalar(select(func.max(Dump.built_at)))
    old = list(
        await session.scalars(
            select(Dump)
            .where(Dump.built_at < cutoff, Dump.built_at < newest)
            .order_by(Dump.built_at)
        )
    )
    for dump in old:
        for key in (dump.csv_key, dump.json_key):
            await s3.delete(
                settings.dumps_endpoint,
                settings.dumps_bucket,
                key,
                settings.dumps_access_key,
                settings.dumps_secret_key,
                settings.dumps_region,
                transport,
            )
        # Gone from the list only once both files are gone from the bucket.
        await session.delete(dump)
        await session.commit()
    if old:
        log.info("Deleted %s data dumps older than %s days", len(old), settings.dumps_keep_days)
    return len(old)


async def due(session: AsyncSession) -> bool:
    last = await session.scalar(select(func.max(Dump.built_at)))
    return last is None or datetime.now(UTC) - last >= EVERY


async def keep_weekly(factory: async_sessionmaker) -> None:
    """In the background: build one when the last is a week old. Checked
    hourly; an advisory lock keeps two servers from both building."""
    await asyncio.sleep(60)
    while True:
        settings = get_settings()
        if settings.dumps_configured:
            try:
                async with factory() as session:
                    locked = await session.scalar(text("SELECT pg_try_advisory_lock(7461)"))
                    if locked:
                        try:
                            if await due(session):
                                await build(session, settings)
                            await prune(session, settings)
                        finally:
                            await session.execute(text("SELECT pg_advisory_unlock(7461)"))
            except Exception:
                log.exception("Building the weekly data dump failed")
        await asyncio.sleep(3600)
