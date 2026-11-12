"""Merging two records of one book into one. *TODO.md: "nothing can merge
two records of one book yet"; Ray, 2026-11-10: next, as contributors adding
books will make duplicates.*

Everything of the book that goes moves to the one kept: its editions (with
their buy links and clicks, which hang off the edition), its recipes and
where they are, its credits (one per author and role), its tags, the
requests for it; the details the kept one lacks (a subtitle, its Open
Library work) come with them. Open proposals to the one that goes are
closed, saying why. Then it's removed.

A recipe's place is keyed by its source with the recipe and the edition
(recipe_locations' composite keys), so moving both under the kept book
means lifting the places off first and putting them back after.

What moved is kept in a record (models/merges.py), so an administrator can
unmerge: *Ray, 2026-11-11, "even if admin only as a check on moderators".*
An unmerge puts the removed book back under its own id and moves back
whatever of it is still with the kept book; anything since added to the
kept book stays there. It's refused when a recipe page now joins the two
(a recipe of one at a page in an edition of the other), which has to be
moved or removed first.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Table, delete, exists, func, insert, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from openlarder import references
from openlarder.models import (
    Author,
    BookMerge,
    BookRequest,
    Edition,
    Proposal,
    Recipe,
    RecipeLocation,
    ShelfBook,
    Source,
    SourceCredit,
    SourceTag,
    Tag,
    User,
)

DECLINED = "The book was merged into “{}”; suggest the change there."


class CantMerge(ValueError):
    """Why, to show beside the button."""


@dataclass
class Plan:
    editions: int
    recipes: int
    credits: int
    # Recipe titles both books have: likely the same recipe twice.
    same_titles: list[str]


def check(gone: Source, kept: Source) -> None:
    if gone.id == kept.id:
        raise CantMerge("A book can't be merged into itself.")
    if gone.kind != "book" or kept.kind != "book":
        raise CantMerge("Only two books are merged here.")


async def plan(session: AsyncSession, gone: Source, kept: Source) -> Plan:
    """What merging would move, for the moderator to check first."""
    check(gone, kept)
    count = lambda model: select(func.count()).where(model.source_id == gone.id)  # noqa: E731
    theirs = aliased(Recipe)
    same = await session.scalars(
        select(Recipe.title)
        .where(
            Recipe.source_id == gone.id,
            exists().where(
                theirs.source_id == kept.id, func.lower(theirs.title) == func.lower(Recipe.title)
            ),
        )
        .order_by(Recipe.title)
        .limit(50)
    )
    return Plan(
        editions=await session.scalar(count(Edition)) or 0,
        recipes=await session.scalar(count(Recipe)) or 0,
        credits=await session.scalar(count(SourceCredit)) or 0,
        same_titles=list(same),
    )


async def _row(session: AsyncSession, table: Table, where: str, **params) -> list[dict]:
    rows = await session.scalars(
        text(f"SELECT to_jsonb(t) FROM {table.name} t WHERE {where}"), params
    )
    return list(rows)


async def _put_back(session: AsyncSession, table: Table, row: dict) -> None:
    """A row as to_jsonb saved it, every column as it was."""
    names = ", ".join(f'"{c.name}"' for c in table.columns)
    await session.execute(
        text(
            f"INSERT INTO {table.name} ({names}) SELECT {names}"
            f" FROM jsonb_populate_record(NULL::{table.name}, CAST(:row AS jsonb))"
        ),
        {"row": json.dumps(row)},
    )


async def _ids(session: AsyncSession, column, *where) -> list[str]:
    return [str(i) for i in await session.scalars(select(column).where(*where))]


async def merge(
    session: AsyncSession, gone: Source, kept: Source, by: User | None = None
) -> BookMerge:
    """Merge gone into kept; the record of it, added to the session."""
    check(gone, kept)
    theirs_credit = aliased(SourceCredit)
    duplicate_credit = exists().where(
        theirs_credit.source_id == kept.id,
        theirs_credit.author_id == SourceCredit.author_id,
        theirs_credit.role == SourceCredit.role,
    )
    tagged = select(SourceTag.tag_id).where(SourceTag.source_id == kept.id)
    saved = {
        "source": (await _row(session, Source.__table__, "id = :id", id=gone.id))[0],
        "editions": await _ids(session, Edition.id, Edition.source_id == gone.id),
        "recipes": await _ids(session, Recipe.id, Recipe.source_id == gone.id),
        "credits": [
            [str(i), p]
            for i, p in await session.execute(
                select(SourceCredit.id, SourceCredit.position).where(
                    SourceCredit.source_id == gone.id, ~duplicate_credit
                )
            )
        ],
        "credits_dropped": [
            r
            for r in await _row(session, SourceCredit.__table__, "source_id = :id", id=gone.id)
            if await session.scalar(
                select(
                    exists().where(
                        SourceCredit.source_id == kept.id,
                        SourceCredit.author_id == uuid.UUID(r["author_id"]),
                        SourceCredit.role == r["role"],
                    )
                )
            )
        ],
        "tags": await _ids(
            session,
            SourceTag.tag_id,
            SourceTag.source_id == gone.id,
            SourceTag.tag_id.not_in(tagged),
        ),
        "tags_dropped": await _ids(
            session, SourceTag.tag_id, SourceTag.source_id == gone.id, SourceTag.tag_id.in_(tagged)
        ),
        "requests": await _ids(session, BookRequest.id, BookRequest.source_id == gone.id),
        "proposals": await _ids(session, Proposal.id, Proposal.source_id == gone.id),
        "declined": await _ids(
            session, Proposal.id, Proposal.source_id == gone.id, Proposal.status == "open"
        ),
        "subtitle": not kept.subtitle and bool(gone.subtitle),
        "work": not kept.open_library_work_id and bool(gone.open_library_work_id),
    }
    # The places, lifted off before their recipes and editions move.
    places = [
        {c.key: getattr(row, c.key) for c in RecipeLocation.__table__.columns}
        for row in await session.scalars(
            select(RecipeLocation).where(RecipeLocation.source_id == gone.id)
        )
    ]
    await session.execute(delete(RecipeLocation).where(RecipeLocation.source_id == gone.id))
    await session.execute(
        update(Edition).where(Edition.source_id == gone.id).values(source_id=kept.id)
    )
    await session.execute(
        update(Recipe).where(Recipe.source_id == gone.id).values(source_id=kept.id)
    )
    if places:
        for place in places:
            place["source_id"] = kept.id
        await session.execute(insert(RecipeLocation), places)

    # Credits: kept's first, then gone's that kept lacks, in their order.
    await session.execute(
        delete(SourceCredit).where(SourceCredit.source_id == gone.id, duplicate_credit)
    )
    after = await session.scalar(
        select(func.coalesce(func.max(SourceCredit.position), 0)).where(
            SourceCredit.source_id == kept.id
        )
    )
    await session.execute(
        update(SourceCredit)
        .where(SourceCredit.source_id == gone.id)
        .values(source_id=kept.id, position=SourceCredit.position + after)
    )

    # Tags: the union.
    await session.execute(
        update(SourceTag)
        .where(SourceTag.source_id == gone.id, SourceTag.tag_id.not_in(tagged))
        .values(source_id=kept.id)
    )
    await session.execute(delete(SourceTag).where(SourceTag.source_id == gone.id))

    await session.execute(
        update(BookRequest).where(BookRequest.source_id == gone.id).values(source_id=kept.id)
    )
    await session.execute(
        update(Proposal)
        .where(Proposal.source_id == gone.id, Proposal.status == "open")
        .values(
            status="declined",
            note=DECLINED.format(kept.title),
            decided_at=func.now(),
        )
    )
    # Kept with the book that stays, so their contributors still see them.
    await session.execute(
        update(Proposal).where(Proposal.source_id == gone.id).values(source_id=kept.id)
    )

    # People's shelves: the book kept, with the edition they said they have.
    # Not in the record: a shelf is private, and an unmerge moves back the
    # ones whose edition goes back.
    kept_shelf = aliased(ShelfBook)
    both = exists().where(kept_shelf.user_id == ShelfBook.user_id, kept_shelf.source_id == kept.id)
    gone_shelf = aliased(ShelfBook)
    await session.execute(
        update(ShelfBook)
        .where(ShelfBook.source_id == kept.id, ShelfBook.edition_id.is_(None))
        .values(
            edition_id=select(gone_shelf.edition_id)
            .where(gone_shelf.user_id == ShelfBook.user_id, gone_shelf.source_id == gone.id)
            .scalar_subquery()
        )
    )
    await session.execute(delete(ShelfBook).where(ShelfBook.source_id == gone.id, both))
    await session.execute(
        update(ShelfBook).where(ShelfBook.source_id == gone.id).values(source_id=kept.id)
    )

    # What kept lacks, from gone; its Open Library work is unique, so it's
    # let go of first.
    subtitle, work = gone.subtitle, gone.open_library_work_id
    await session.delete(gone)
    await session.flush()
    if not kept.subtitle and subtitle:
        kept.subtitle = subtitle
    if not kept.open_library_work_id and work:
        kept.open_library_work_id = work
    await session.flush()
    # Page references ("p. 14") now resolve across both books' recipes.
    await references.relink(session, kept.id)
    record = BookMerge(
        gone_id=gone.id,
        gone_title=gone.title,
        kept_id=kept.id,
        merged_by=by.id if by else None,
        saved=saved,
    )
    session.add(record)
    await session.flush()
    return record


def _uuids(values: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(v) for v in values]


async def unmerge(session: AsyncSession, record: BookMerge, by: User | None = None) -> Source:
    """Take a merge apart again; the book put back."""
    if record.undone_at is not None:
        raise CantMerge("It's been unmerged already.")
    if await session.get(Source, record.gone_id) is not None:
        raise CantMerge(f"“{record.gone_title}” is back already.")
    kept = await session.get(Source, record.kept_id)
    if kept is None:
        raise CantMerge(
            "The book it was merged into is gone, perhaps merged into another in turn:"
            " unmerge that first."
        )
    saved = record.saved
    gone_id = record.gone_id
    # What's still with the kept book, of what moved.
    editions = await session.scalars(
        select(Edition.id).where(
            Edition.id.in_(_uuids(saved["editions"])), Edition.source_id == kept.id
        )
    )
    editions = list(editions)
    recipes = list(
        await session.scalars(
            select(Recipe.id).where(
                Recipe.id.in_(_uuids(saved["recipes"])), Recipe.source_id == kept.id
            )
        )
    )
    crossing = list(
        await session.scalars(
            select(Recipe.title)
            .join(RecipeLocation, RecipeLocation.recipe_id == Recipe.id)
            .where(
                RecipeLocation.source_id == kept.id,
                or_(
                    (RecipeLocation.recipe_id.in_(recipes))
                    & (
                        RecipeLocation.edition_id.is_(None)
                        | RecipeLocation.edition_id.not_in(editions)
                    ),
                    RecipeLocation.edition_id.in_(editions)
                    & RecipeLocation.recipe_id.not_in(recipes),
                ),
            )
            .order_by(Recipe.title)
        )
    )
    if crossing:
        names = ", ".join(f"“{t}”" for t in sorted(set(crossing))[:3])
        raise CantMerge(
            f"{len(crossing)} recipe {'page joins' if len(crossing) == 1 else 'pages join'}"
            f" the two books ({names}): a recipe of one at a page in an edition of the"
            " other. Move or remove those pages first."
        )

    row = saved["source"]
    # The details kept took from it, while they're still as it gave them.
    if saved["subtitle"] and kept.subtitle == row.get("subtitle"):
        kept.subtitle = None
    if saved["work"] and kept.open_library_work_id == row.get("open_library_work_id"):
        kept.open_library_work_id = None
    await session.flush()
    await _put_back(session, Source.__table__, row)

    places = [
        {c.key: getattr(p, c.key) for c in RecipeLocation.__table__.columns}
        for p in await session.scalars(
            select(RecipeLocation).where(RecipeLocation.recipe_id.in_(recipes))
        )
    ]
    await session.execute(delete(RecipeLocation).where(RecipeLocation.recipe_id.in_(recipes)))
    await session.execute(update(Edition).where(Edition.id.in_(editions)).values(source_id=gone_id))
    # Shelves holding one of its editions go back with it.
    await session.execute(
        update(ShelfBook)
        .where(ShelfBook.source_id == kept.id, ShelfBook.edition_id.in_(editions))
        .values(source_id=gone_id)
    )
    await session.execute(update(Recipe).where(Recipe.id.in_(recipes)).values(source_id=gone_id))
    if places:
        for place in places:
            place["source_id"] = gone_id
        await session.execute(insert(RecipeLocation), places)

    for credit_id, position in saved["credits"]:
        await session.execute(
            update(SourceCredit)
            .where(SourceCredit.id == uuid.UUID(credit_id), SourceCredit.source_id == kept.id)
            .values(source_id=gone_id, position=position)
        )
    # The ones it dropped, as kept had them too: back, while the author is.
    for credit in saved["credits_dropped"]:
        if await session.get(Author, uuid.UUID(credit["author_id"])) is not None:
            await _put_back(session, SourceCredit.__table__, credit)

    await session.execute(
        update(SourceTag)
        .where(SourceTag.source_id == kept.id, SourceTag.tag_id.in_(_uuids(saved["tags"])))
        .values(source_id=gone_id)
    )
    for tag_id in _uuids(saved["tags_dropped"]):
        if await session.get(Tag, tag_id) is not None:
            session.add(SourceTag(source_id=gone_id, tag_id=tag_id))

    await session.execute(
        update(BookRequest)
        .where(BookRequest.id.in_(_uuids(saved["requests"])), BookRequest.source_id == kept.id)
        .values(source_id=gone_id)
    )
    await session.execute(
        update(Proposal)
        .where(Proposal.id.in_(_uuids(saved["proposals"])), Proposal.source_id == kept.id)
        .values(source_id=gone_id)
    )
    await session.execute(
        update(Proposal)
        .where(
            Proposal.id.in_(_uuids(saved["declined"])),
            Proposal.status == "declined",
            Proposal.decided_by.is_(None),
            Proposal.note.startswith(DECLINED.split("“")[0]),
        )
        .values(status="open", note=None, decided_at=None)
    )
    await session.flush()
    for source_id in (kept.id, gone_id):
        await references.relink(session, source_id)
    record.undone_at = datetime.now(UTC)
    record.undone_by = by.id if by else None
    await session.flush()
    return await session.get(Source, gone_id)
