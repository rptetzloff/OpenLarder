"""Emptying the catalog, so the household index can be imported again.

    python -m openlarder.reset                # the catalog
    python -m openlarder.reset --everything   # and accounts, groups, requests…

In the app's container (Coolify's terminal for it). It counts what it would
delete, then asks for the site's host name typed out; nothing is deleted
without it. `--confirm <host>` answers that in advance, for a script.

*Ray, 2026-11-10.* The catalog goes, family collections included: sources
and all that hangs off them (editions, buy links and their clicks, issues,
episodes, web pages, credits), recipes and their lines, ingredients,
aliases and swaps, authors, and the tags given to sources and recipes. With
them: people's larder items (the lists stay, empty), the catalog's edit
history, flags, reports, suggested changes, n8n's suggestions and
embeddings, and import history. Accounts, groups, larder lists and requests
stay; requests are unlinked from their books, to link again as each comes
back (migration 0050).

`--everything` empties those too: every account with its sessions, API keys,
larder lists and group memberships, every group, request and vote, all edit
history, and the list of published data dumps (the files stay in their
bucket; a fresh dump is built within the hour). Anyone signing in after it
starts again as a new user, the owner too: make yourself owner again by
hand (roles.py).

Never emptied: the tag list (the seeded diets, courses, cuisines and
techniques, and any added since, which the app expects), FoodData
Central's foods (reference data, not the catalog's), and the schema's
version.

One transaction: TRUNCATE, which neither fires the history triggers nor
takes long. It refuses a table something kept still points at, so the one
such link, a request's book, is let go for the length of a catalog reset
and put back.
"""

import argparse
import asyncio
import sys
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.config import get_settings
from openlarder.db import dispose_engine, session_factory

# The catalog. Named, never CASCADE: a table left out that points at one of
# these makes TRUNCATE refuse, rather than empty it unseen.
CATALOG = (
    "sources",
    "editions",
    "purchase_links",
    "purchase_clicks",
    "grocery_clicks",
    "issues",
    "episodes",
    "web_pages",
    "source_credits",
    "source_tags",
    "source_groups",
    "authors",
    "author_links",
    "recipes",
    "recipe_locations",
    "recipe_ingredients",
    "ingredient_options",
    "recipe_tags",
    "recipe_flags",
    "ingredients",
    "ingredient_aliases",
    "ingredient_embeddings",
    "substitutions",
    "larder_items",
    "proposals",
    "reports",
    "suggestions",
    "import_runs",
    "import_run_lines",
    "book_merges",
    "ingredient_link_suggestions",
)
# Emptied too with --everything. (revisions: a catalog reset deletes the
# catalog's history from it, and this all of it.)
PEOPLE = (
    "users",
    "user_sessions",
    "api_keys",
    "api_usage",
    "groups",
    "group_members",
    "group_invites",
    "larder_lists",
    "larder_list_groups",
    "book_requests",
    "request_votes",
    "dumps",
    "daily_counts",
    "revisions",
)
# Never emptied. A new table must be named in one of the three lists
# (tests/test_reset.py), so the reset never misses one.
KEPT = ("alembic_version", "tags", "fdc_foods")
# A catalog reset's history kept: the tag list's.
HISTORY_KEPT = ("tags",)

_REQUEST_LINK = "fk_book_requests_source_id_sources"


async def _count(session: AsyncSession, table: str) -> int:
    return await session.scalar(text(f"SELECT count(*) FROM {table}"))


async def counts(session: AsyncSession, everything: bool = False) -> dict[str, int]:
    """Rows in each table the reset empties."""
    found = {t: await _count(session, t) for t in CATALOG}
    if everything:
        found |= {t: await _count(session, t) for t in PEOPLE}
    else:
        found["revisions"] = await session.scalar(
            text("SELECT count(*) FROM revisions WHERE table_name <> ALL(:kept)"),
            {"kept": list(HISTORY_KEPT)},
        )
    return found


async def reset(session: AsyncSession, everything: bool = False) -> None:
    """Empty the catalog, or with everything all but KEPT. The caller commits."""
    if everything:
        await session.execute(text(f"TRUNCATE {', '.join(CATALOG + PEOPLE)}"))
        return
    await session.execute(
        text("UPDATE book_requests SET source_id = NULL WHERE source_id IS NOT NULL")
    )
    await session.execute(text(f"ALTER TABLE book_requests DROP CONSTRAINT {_REQUEST_LINK}"))
    await session.execute(text(f"TRUNCATE {', '.join(CATALOG)}"))
    await session.execute(
        text(
            f"ALTER TABLE book_requests ADD CONSTRAINT {_REQUEST_LINK}"
            " FOREIGN KEY (source_id) REFERENCES sources (id) ON DELETE SET NULL"
        )
    )
    await session.execute(
        text("DELETE FROM revisions WHERE table_name <> ALL(:kept)"),
        {"kept": list(HISTORY_KEPT)},
    )


def _host() -> str:
    """The site's host name, which is the confirmation: from the public URL,
    or the database's host when there's none."""
    settings = get_settings()
    url = settings.public_url or settings.database_url
    return urlsplit(url).hostname or "localhost"


async def _main(confirm: str | None, everything: bool) -> int:
    host = _host()
    async with session_factory()() as session:
        found = await counts(session, everything)
        print("This deletes, for good:")
        for table, n in found.items():
            if n:
                print(f"  {n:>9,}  {table}")
        if not any(found.values()):
            print("  nothing: it's all empty already.")
            return 0
        if everything:
            print(
                "Everything goes but the tag list. Anyone signing in afterwards is a new user,"
                " you too: make yourself owner again by hand."
            )
        else:
            print("Accounts, groups, larder lists, requests and the tag list stay.")
        try:
            answer = confirm if confirm is not None else input(f"Type {host} to go ahead: ")
        except EOFError:
            # No terminal to ask on: not confirmed.
            answer = ""
        if answer.strip() != host:
            print("Not confirmed; nothing was deleted.")
            return 1
        await reset(session, everything)
        await session.commit()
    print("Emptied, all but the tag list." if everything else "The catalog is empty.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m openlarder.reset", description=__doc__)
    parser.add_argument("--confirm", metavar="HOST", help="the site's host name, typed in advance")
    parser.add_argument(
        "--everything",
        action="store_true",
        help="also delete accounts, groups, requests, all history and the dump list",
    )
    args = parser.parse_args(argv)

    async def run() -> int:
        try:
            return await _main(args.confirm, args.everything)
        finally:
            await dispose_engine()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
