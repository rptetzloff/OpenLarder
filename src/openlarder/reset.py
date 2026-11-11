"""Emptying the catalog, so the household index can be imported again.

    python -m openlarder.reset

In the app's container (Coolify's terminal for it). It counts what it would
delete, then asks for the site's host name typed out; nothing is deleted
without it. `--confirm <host>` answers that in advance, for a script.

*Ray, 2026-11-10.* Everything in the catalog goes, family collections
included: sources and all that hangs off them (editions, buy links and
their clicks, issues, episodes, web pages, credits), recipes and their
lines, ingredients, aliases and swaps, authors, and the tags given to
sources and recipes. With them: people's larder items (the lists stay,
empty), the catalog's edit history, flags, reports, suggested changes, n8n's
suggestions and embeddings, and import history.

Kept: accounts and their sessions and API keys, groups, larder lists,
requests (unlinked from their books, to link again as each comes back:
migration 0050), the tag list (the seeded diets, courses, cuisines and
techniques, and any added since), the history of tags, and the data dumps
already published.

One transaction: TRUNCATE, which neither fires the history triggers nor
takes long. It refuses a table something kept still points at, so the one
such link, a request's book, is let go for the length of it and put back.
"""

import argparse
import asyncio
import sys
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.config import get_settings
from openlarder.db import dispose_engine, session_factory

# Every table emptied. Named, never CASCADE: a table left out that points at
# one of these makes TRUNCATE refuse, rather than empty it unseen.
CATALOG = (
    "sources",
    "editions",
    "purchase_links",
    "purchase_clicks",
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
)
# Every other table, kept: a new table must be named in one list or the
# other (tests/test_reset.py), so the reset never misses one.
KEPT = (
    "alembic_version",
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
    "tags",
    "dumps",
    "revisions",
)
# Kept tables' history: only the tag list's is kept.
HISTORY_KEPT = ("tags",)

_REQUEST_LINK = "fk_book_requests_source_id_sources"


async def counts(session: AsyncSession) -> dict[str, int]:
    """Rows in each table the reset empties, and the catalog history."""
    found = {t: await session.scalar(text(f"SELECT count(*) FROM {t}")) for t in CATALOG}
    found["revisions"] = await session.scalar(
        text("SELECT count(*) FROM revisions WHERE table_name <> ALL(:kept)"),
        {"kept": list(HISTORY_KEPT)},
    )
    return found


async def reset(session: AsyncSession) -> None:
    """Empty the catalog. The caller commits."""
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


async def _main(confirm: str | None) -> int:
    host = _host()
    async with session_factory()() as session:
        found = await counts(session)
        print("This deletes, for good:")
        for table, n in found.items():
            if n:
                print(f"  {n:>9,}  {table}")
        if not any(found.values()):
            print("  nothing: the catalog is empty already.")
            return 0
        print("Accounts, groups, larder lists, requests and the tag list stay.")
        try:
            answer = confirm if confirm is not None else input(f"Type {host} to go ahead: ")
        except EOFError:
            # No terminal to ask on: not confirmed.
            answer = ""
        if answer.strip() != host:
            print("Not confirmed; nothing was deleted.")
            return 1
        await reset(session)
        await session.commit()
    print("The catalog is empty.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m openlarder.reset", description=__doc__)
    parser.add_argument("--confirm", metavar="HOST", help="the site's host name, typed in advance")
    args = parser.parse_args(argv)

    async def run() -> int:
        try:
            return await _main(args.confirm)
        finally:
            await dispose_engine()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
