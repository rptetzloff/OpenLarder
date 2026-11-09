"""Filling in authors' Wikidata facts (wikidata.py), a batch at a time.

An author is found on Wikidata by the Wikidata ID it has, or else by its
Open Library ID. One found by Open Library ID takes the item's Wikidata ID,
unless another author has it already: two authors on one item are usually
one person entered twice, so they're reported to merge by hand rather than
guessed at. An author whose item isn't found keeps no facts, and is asked
about again after RECHECK, since items are added.
"""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta

import httpx2
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import wikidata
from openlarder.models import Author

BATCH = 50
RECHECK = timedelta(days=30)


@dataclass
class Clash:
    """An author the item fits, and the author who has its Wikidata ID."""

    author_id: uuid.UUID
    name: str
    other_id: uuid.UUID
    other_name: str


@dataclass
class Checked:
    checked: int = 0
    found: int = 0
    clashes: list[Clash] = field(default_factory=list)


def _q_number(wikidata_id: str) -> int:
    return int(wikidata_id[1:])


def _set(author: Author, facts: wikidata.Facts | None) -> None:
    author.born_year = facts.born_year if facts else None
    author.died_year = facts.died_year if facts else None
    author.country = facts.country if facts else None
    author.website = facts.website if facts else None
    author.wikidata_checked_at = func.now()


async def check(
    session: AsyncSession,
    authors: list[Author],
    transport: httpx2.AsyncBaseTransport | None = None,
) -> Checked:
    """Ask Wikidata about these authors and record what it says. Raises
    wikidata.Unavailable, changing nothing, if it can't be asked."""
    found = await wikidata.lookup(
        open_library_ids=[
            a.open_library_author_id
            for a in authors
            if a.open_library_author_id and not a.wikidata_id
        ],
        wikidata_ids=[a.wikidata_id for a in authors if a.wikidata_id],
        transport=transport,
    )
    result = Checked()
    # Who holds each Wikidata ID found, this batch's authors included, and
    # those taken as the batch goes.
    held = dict(
        (
            await session.execute(
                select(Author.wikidata_id, Author).where(Author.wikidata_id.in_(list(found)))
            )
        ).all()
    )
    for author in authors:
        result.checked += 1
        if author.wikidata_id:
            facts = found.get(author.wikidata_id)
        else:
            fits = sorted(
                (f for f in found.values() if author.open_library_author_id in f.open_library_ids),
                key=lambda f: _q_number(f.wikidata_id),
            )
            facts = fits[0] if fits else None
            if facts is not None:
                other = held.get(facts.wikidata_id)
                if other is not None and other.id != author.id:
                    result.clashes.append(Clash(author.id, author.name, other.id, other.name))
                    facts = None
                else:
                    author.wikidata_id = facts.wikidata_id
                    held[facts.wikidata_id] = author
        _set(author, facts)
        result.found += facts is not None
    await session.flush()
    return result


def due():
    """Authors Wikidata could know (by either ID), never asked or not lately."""
    return select(Author).where(
        or_(Author.open_library_author_id.is_not(None), Author.wikidata_id.is_not(None)),
        or_(
            Author.wikidata_checked_at.is_(None),
            Author.wikidata_checked_at < func.now() - RECHECK,
        ),
    )
