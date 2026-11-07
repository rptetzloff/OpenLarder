"""Adding a book to the catalog from what Open Library returned.

A book is a Work with one or more Editions. An ISBN names one edition, so a
second ISBN for a book already in the catalog joins it as another edition,
matched by Open Library's work ID. Authors are matched by Open Library's
author ID and created when new; a work's credits are written when the work
is created and left alone after, so adding an edition never rewrites them.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.models import Author, Edition, Work, WorkCredit
from openlarder.openlibrary import FoundBook


class AlreadyIndexed(Exception):
    def __init__(self, work_id: uuid.UUID) -> None:
        super().__init__(str(work_id))
        self.work_id = work_id


async def add_book(session: AsyncSession, found: FoundBook) -> uuid.UUID:
    """Store the edition, and its work and authors if new; return the work's ID."""
    existing = await session.scalar(
        select(Edition.work_id).where(
            (Edition.isbn13 == found.isbn13)
            | (Edition.open_library_edition_id == (found.edition_id or None))
        )
    )
    if existing is not None:
        raise AlreadyIndexed(existing)

    work = None
    if found.work_id:
        work = await session.scalar(select(Work).where(Work.open_library_work_id == found.work_id))
    if work is None:
        work = Work(title=found.title, subtitle=found.subtitle, open_library_work_id=found.work_id)
        session.add(work)
        await session.flush()
        for position, found_author in enumerate(found.authors, start=1):
            author = await session.scalar(
                select(Author).where(Author.open_library_author_id == found_author.open_library_id)
            )
            if author is None:
                author = Author(
                    name=found_author.name, open_library_author_id=found_author.open_library_id
                )
                session.add(author)
                await session.flush()
            session.add(
                WorkCredit(
                    work_id=work.id,
                    author_id=author.id,
                    position=position,
                    credited_as=found_author.name,
                )
            )

    session.add(
        Edition(
            work_id=work.id,
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
