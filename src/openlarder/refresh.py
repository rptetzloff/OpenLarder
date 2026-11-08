"""Checking a linked book against Open Library, and taking what an admin picks.

A book is read from Open Library once, when it is added or linked, and
nothing re-reads it, so a fix made there later never arrives. Nor should
one arrive by itself: what is stored here may be a fix made here ("This Is
Camino", "Russell Moore"), and nothing records which fields were fixed. So
a check lists every difference between what is stored and what Open
Library says now, beside each other, and an admin ticks the ones to take.
*Ray, 2026-11-08: "we need the ability to pull fresh from open library".*

What is compared: the work's title and subtitle; who it credits, by Open
Library author; each credited Open Library author's own name and kind; and,
for each edition linked to Open Library, its title, publisher, year and
cover. ISBNs and Open Library IDs are what tie the records together, so
they are not offered. Names from Open Library are cleaned first
(openlibrary.clean_name), so "Moore, Russell (Chef)" is offered as
"Russell Moore".

Applying fetches again rather than trusting the page's copy, and takes only
the keys asked for that still differ.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx2
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import books, openlibrary
from openlarder.models import Author, Edition, Source, SourceCredit


@dataclass
class Difference:
    # Stable for a book: "title", "credits", "author:<id>:name",
    # "edition:<id>:publisher", …; what the admin's ticks send back.
    key: str
    label: str
    ours: str | None
    theirs: str | None
    apply: Callable[[], Awaitable[None]] = field(repr=False)
    # Values are cover image addresses rather than text.
    cover: bool = False


class NotLinked(ValueError):
    """The book has no Open Library work to check against."""


def _cover(cover_id: int | None) -> str | None:
    return openlibrary.cover_url(cover_id) if cover_id else None


async def check(
    session: AsyncSession, work: Source, transport: httpx2.AsyncBaseTransport | None = None
) -> list[Difference]:
    """Every difference between the book as stored and Open Library now.
    Raises NotLinked, or openlibrary's NotFound and Unavailable."""
    if not work.open_library_work_id:
        raise NotLinked("This book isn't linked to Open Library yet.")
    found = await openlibrary.find(("work", work.open_library_work_id), transport)
    editions = (
        await session.scalars(
            select(Edition)
            .where(Edition.source_id == work.id, Edition.open_library_edition_id.is_not(None))
            .order_by(Edition.published_year.desc().nulls_last(), Edition.isbn13)
        )
    ).all()
    printings = [
        await openlibrary.find(("edition", e.open_library_edition_id), transport)
        for e in editions
        if e.open_library_edition_id
    ]
    out: list[Difference] = []

    def setter(obj: object, attr: str, value: object) -> Callable[[], Awaitable[None]]:
        async def apply() -> None:
            setattr(obj, attr, value)

        return apply

    if found.title != work.title:
        out.append(
            Difference(
                "title", "Title", work.title, found.title, apply=setter(work, "title", found.title)
            )
        )
    # Read as adding a book reads it: the work's, else an edition's.
    subtitle = found.subtitle or next((p.subtitle for p in printings if p.subtitle), None)
    # Something Open Library lacks isn't offered as a blank: that would only
    # ever wipe what was entered here.
    if subtitle and subtitle != work.subtitle:
        out.append(
            Difference(
                "subtitle",
                "Subtitle",
                work.subtitle,
                subtitle,
                apply=setter(work, "subtitle", subtitle),
            )
        )

    credits = (
        await session.execute(
            select(SourceCredit, Author)
            .join(Author, Author.id == SourceCredit.author_id)
            .where(SourceCredit.source_id == work.id)
            .order_by(SourceCredit.position)
        )
    ).all()
    ours = [a.open_library_author_id for _, a in credits]
    theirs = [a.open_library_id for a in found.authors]
    if ours != theirs:
        out.append(
            Difference(
                "credits",
                "Credited",
                ", ".join(c.credited_as for c, _ in credits) or None,
                ", ".join(a.name for a in found.authors) or None,
                apply=lambda: _take_credits(session, work, found.authors),
            )
        )
    by_id = {a.open_library_author_id: a for _, a in credits if a.open_library_author_id}
    for found_author in found.authors:
        author = by_id.get(found_author.open_library_id)
        if author is None:
            continue
        if author.name != found_author.name:
            out.append(
                Difference(
                    f"author:{author.id}:name",
                    f"{author.name}: the author's own name",
                    author.name,
                    found_author.name,
                    apply=setter(author, "name", found_author.name),
                )
            )
        if author.kind != found_author.kind:
            out.append(
                Difference(
                    f"author:{author.id}:kind",
                    f"{author.name}: person or organisation",
                    author.kind,
                    found_author.kind,
                    apply=setter(author, "kind", found_author.kind),
                )
            )

    for edition, printing in zip(editions, printings, strict=True):
        name = f"Edition{f' {edition.isbn13}' if edition.isbn13 else ''}"
        # Only when it differs from the work's, as the model says.
        title = printing.edition_title
        if title and title.casefold() == (found.title or work.title).casefold():
            title = None
        for attr, label, theirs_value in (
            ("title", "title", title),
            ("publisher", "publisher", printing.publisher),
            ("published_year", "year", printing.published_year),
        ):
            ours_value = getattr(edition, attr)
            if theirs_value is not None and theirs_value != ours_value:
                out.append(
                    Difference(
                        f"edition:{edition.id}:{attr}",
                        f"{name}: {label}",
                        None if ours_value is None else str(ours_value),
                        str(theirs_value),
                        apply=setter(edition, attr, theirs_value),
                    )
                )
        if printing.cover_id and printing.cover_id != edition.open_library_cover_id:
            out.append(
                Difference(
                    f"edition:{edition.id}:cover",
                    f"{name}: cover",
                    _cover(edition.open_library_cover_id),
                    _cover(printing.cover_id),
                    cover=True,
                    apply=setter(edition, "open_library_cover_id", printing.cover_id),
                )
            )
    return out


async def _take_credits(
    session: AsyncSession, work: Source, found: list[openlibrary.FoundAuthor]
) -> None:
    """Credit the book as Open Library does, in its order, as authors."""
    before = list(
        await session.scalars(
            select(SourceCredit.author_id).where(SourceCredit.source_id == work.id)
        )
    )
    await session.execute(delete(SourceCredit).where(SourceCredit.source_id == work.id))
    for position, found_author in enumerate(found, start=1):
        author = await session.scalar(
            select(Author).where(Author.open_library_author_id == found_author.open_library_id)
        )
        if author is None:
            author = Author(
                name=found_author.name,
                kind=found_author.kind,
                open_library_author_id=found_author.open_library_id,
            )
            session.add(author)
            await session.flush()
        session.add(
            SourceCredit(
                source_id=work.id,
                author_id=author.id,
                position=position,
                credited_as=found_author.name,
            )
        )
    await session.flush()
    await books.drop_uncredited(session, before)


async def apply(
    session: AsyncSession,
    work: Source,
    keys: set[str],
    transport: httpx2.AsyncBaseTransport | None = None,
) -> int:
    """Take the differences named by keys that still exist; how many. A key
    from another book matches nothing, since the differences are this book's."""
    taken = 0
    for difference in await check(session, work, transport):
        if difference.key in keys:
            await difference.apply()
            taken += 1
    await session.flush()
    return taken
