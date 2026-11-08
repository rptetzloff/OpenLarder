"""Merging two records of one author into one.

Two records of one person arise: Open Library keeps two (Jennifer McLagan,
once as "Mclagan"), or one was typed before typed names matched Open
Library's. *Ray, 2026-11-08: "we need a merge authors function".* Merging
moves everything to the record kept: its credits, links and outside
records. Each source still prints the name it prints (credited_as); only
the record behind it changes.
"""

from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from openlarder.models import Author, AuthorLink, SourceCredit


async def merge(session: AsyncSession, gone: Author, kept: Author) -> None:
    """Fold gone into kept. Where both credit one source in one role, kept's
    credit stays; where both link one address, kept's link stays. An outside
    record (Open Library, Wikidata) moves to kept when kept has none; when
    both have one, kept's stays."""
    if gone.id == kept.id:
        raise ValueError("An author can't be merged into themselves.")

    theirs = aliased(SourceCredit)
    await session.execute(
        delete(SourceCredit).where(
            SourceCredit.author_id == gone.id,
            exists().where(
                theirs.author_id == kept.id,
                theirs.source_id == SourceCredit.source_id,
                theirs.role == SourceCredit.role,
            ),
        )
    )
    await session.execute(
        update(SourceCredit).where(SourceCredit.author_id == gone.id).values(author_id=kept.id)
    )

    kept_urls = select(AuthorLink.url).where(AuthorLink.author_id == kept.id)
    await session.execute(
        delete(AuthorLink).where(AuthorLink.author_id == gone.id, AuthorLink.url.in_(kept_urls))
    )
    await session.execute(
        update(AuthorLink).where(AuthorLink.author_id == gone.id).values(author_id=kept.id)
    )

    # Unique columns: off the record going before onto the one kept.
    moving = {
        column: getattr(gone, column)
        for column in ("open_library_author_id", "wikidata_id")
        if getattr(kept, column) is None and getattr(gone, column) is not None
    }
    await session.delete(gone)
    await session.flush()
    for column, value in moving.items():
        setattr(kept, column, value)
    await session.flush()
