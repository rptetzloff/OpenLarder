"""Adding a book to the catalog from what Open Library returned.

A book is a Source with one or more Editions. An ISBN names one edition, so a
second ISBN for a book already in the catalog joins it as another edition,
matched by Open Library's work ID. Authors are matched by Open Library's
author ID and created when new; a work's credits are written when the work
is created and left alone after, so adding an edition never rewrites them.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, exists, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.models import Author, Edition, Source, SourceCredit
from openlarder.openlibrary import FoundBook


class AlreadyIndexed(Exception):
    def __init__(self, source_id: uuid.UUID) -> None:
        super().__init__(str(source_id))
        self.source_id = source_id


async def add_book(session: AsyncSession, found: FoundBook) -> uuid.UUID:
    """Store the edition, and its work and authors if new; return the work's ID."""
    existing = await session.scalar(
        select(Edition.source_id).where(
            ((Edition.isbn13 == found.isbn13) if found.isbn13 else false())
            | (
                (Edition.open_library_edition_id == found.edition_id)
                if found.edition_id
                else false()
            )
        )
    )
    if existing is not None:
        raise AlreadyIndexed(existing)

    work = None
    if found.open_library_work_id:
        work = await session.scalar(
            select(Source).where(Source.open_library_work_id == found.open_library_work_id)
        )
    if work is None:
        work = Source(
            title=found.title,
            subtitle=found.subtitle,
            open_library_work_id=found.open_library_work_id,
        )
        session.add(work)
        await session.flush()
        for position, found_author in enumerate(found.authors, start=1):
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

    session.add(
        Edition(
            source_id=work.id,
            # Only when it differs from the work's, as for a retitled edition.
            title=(
                found.edition_title
                if found.edition_title and found.edition_title.casefold() != work.title.casefold()
                else None
            ),
            isbn13=found.isbn13,
            publisher=found.publisher,
            published_year=found.published_year,
            open_library_edition_id=found.edition_id or None,
            open_library_cover_id=found.cover_id,
        )
    )
    await session.flush()
    return work.id


async def add_without_isbn(
    session: AsyncSession,
    title: str,
    authors: list[str],
    year: int | None,
    isbn13: str | None = None,
) -> tuple[uuid.UUID, bool]:
    """A book Open Library can't supply, from what the person adding it says.

    Returns (work ID, existed). Used for books with no ISBN, and for books
    whose ISBN Open Library doesn't know, which keep that ISBN: without it,
    an import's recipes for the book, which name it by ISBN, find no edition.
    That lost The Heritage Cookbook's 324 recipes on the first import.

    Matched by ISBN when there is one, then by title among books that didn't
    come from Open Library, so a second import finds the first's. A match
    found by title whose one edition has no ISBN is given this one, which
    repairs books added before the ISBN was kept. Authors are matched by
    exact name among those without an Open Library ID, the nearest thing to
    identity there is without one; two people sharing a name is a merge for
    review.
    """
    if isbn13:
        by_isbn = await session.scalar(select(Edition.source_id).where(Edition.isbn13 == isbn13))
        if by_isbn is not None:
            return by_isbn, True
    existing = await session.scalar(
        select(Source.id).where(
            func.lower(Source.title) == title.lower(), Source.open_library_work_id.is_(None)
        )
    )
    if existing is not None:
        editions = (
            await session.scalars(select(Edition).where(Edition.source_id == existing))
        ).all()
        if isbn13 and len(editions) == 1 and editions[0].isbn13 is None:
            editions[0].isbn13 = isbn13
            await session.flush()
        return existing, True
    work = Source(title=title)
    session.add(work)
    await session.flush()
    for position, name in enumerate(authors, start=1):
        author = await author_named(session, name)
        session.add(
            SourceCredit(
                source_id=work.id, author_id=author.id, position=position, credited_as=name
            )
        )
    session.add(Edition(source_id=work.id, published_year=year, isbn13=isbn13))
    await session.flush()
    return work.id, False


# Editing a book


ROLES = ("author", "editor", "contributor", "photographer", "illustrator", "translator")


class InvalidBook(ValueError):
    """The reason is written to be shown beside the form."""


@dataclass
class CreditEdit:
    # The author of one of the book's current credits, or None for a new name.
    author_id: uuid.UUID | None
    name: str
    role: str


@dataclass
class EditionEdit:
    id: uuid.UUID
    title: str | None
    publisher: str | None
    published_year: int | None


def _squash(text: str | None) -> str | None:
    return " ".join((text or "").split()) or None


async def edit_book(
    session: AsyncSession,
    work: Source,
    title: str,
    subtitle: str | None,
    credits: list[CreditEdit],
    editions: list[EditionEdit],
) -> None:
    """Change what a book says about itself: its title, subtitle, credits in
    order, and its editions' title, publisher and year. ISBNs and Open
    Library IDs identify the book, so they aren't edited here.

    A credit keeps its author when it names one already credited, and the
    printed name changes. That author's own name changes too when nothing
    else depends on it: no Open Library record, whose name wins, and no
    other book. A new name is matched as add_without_isbn matches one. An
    author left with no book and no outside record is deleted.
    """
    work.title = _squash(title) or ""
    if not work.title:
        raise InvalidBook("Give the book its title.")
    work.subtitle = _squash(subtitle)

    current = {
        c.author_id: c
        for c in await session.scalars(
            select(SourceCredit).where(SourceCredit.source_id == work.id)
        )
    }
    rows: list[tuple[Author, str, str]] = []
    for credit in credits:
        name = _squash(credit.name)
        if not name:
            raise InvalidBook("Every credit needs a name; remove the empty one.")
        if credit.role not in ROLES:
            raise InvalidBook(f"“{credit.role}” isn't a role a book credits.")
        if credit.author_id is not None:
            if credit.author_id not in current:
                raise InvalidBook("A credit names an author this book doesn't have.")
            author = await session.get_one(Author, credit.author_id)
            if author.open_library_author_id is None and not await _elsewhere(
                session, author.id, work.id
            ):
                author.name = name
        else:
            author = await author_named(session, name)
        rows.append((author, name, credit.role))
    seen: set[tuple[uuid.UUID, str]] = set()
    for author, name, role in rows:
        if (author.id, role) in seen:
            raise InvalidBook(f"{name} is credited twice as {role}.")
        seen.add((author.id, role))

    await session.execute(delete(SourceCredit).where(SourceCredit.source_id == work.id))
    for position, (author, name, role) in enumerate(rows, start=1):
        session.add(
            SourceCredit(
                source_id=work.id,
                author_id=author.id,
                position=position,
                role=role,
                credited_as=name,
            )
        )
    await session.flush()
    kept = {author.id for author, _, _ in rows}
    await drop_uncredited(session, [a for a in current if a not in kept])

    own = {
        e.id: e for e in await session.scalars(select(Edition).where(Edition.source_id == work.id))
    }
    for change in editions:
        edition = own.get(change.id)
        if edition is None:
            raise InvalidBook("An edition in the form isn't this book's.")
        year = change.published_year
        if year is not None and not 1400 <= year <= 2200:
            raise InvalidBook(f"{year} can't be the year an edition was published.")
        edition_title = _squash(change.title)
        # Only when it differs from the book's, as the model says.
        edition.title = None if edition_title == work.title else edition_title
        edition.publisher = _squash(change.publisher)
        edition.published_year = year
    await session.flush()


async def _elsewhere(session: AsyncSession, author_id: uuid.UUID, source_id: uuid.UUID) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(
                    SourceCredit.author_id == author_id, SourceCredit.source_id != source_id
                )
            )
        )
    )


async def drop_uncredited(session: AsyncSession, author_ids: list[uuid.UUID]) -> None:
    """Delete those of these authors no book credits now, unless an outside
    record (Open Library, Wikidata) says who they are."""
    if author_ids:
        await session.execute(
            delete(Author).where(
                Author.id.in_(author_ids),
                Author.open_library_author_id.is_(None),
                Author.wikidata_id.is_(None),
                ~exists().where(SourceCredit.author_id == Author.id),
            )
        )


async def author_named(session: AsyncSession, name: str) -> Author:
    """The author a typed name means: one by exactly that name among those
    without an Open Library record, the nearest thing to identity there is
    without one, or a new author. Two people sharing a name is a merge for
    review."""
    author = await session.scalar(
        select(Author).where(
            func.lower(Author.name) == name.lower(), Author.open_library_author_id.is_(None)
        )
    )
    if author is None:
        author = Author(name=name)
        session.add(author)
        await session.flush()
    return author
