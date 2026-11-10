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
"""

from dataclasses import dataclass

from sqlalchemy import delete, exists, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from openlarder import references
from openlarder.models import (
    BookRequest,
    Edition,
    Proposal,
    Recipe,
    RecipeLocation,
    Source,
    SourceCredit,
    SourceTag,
)


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


async def merge(session: AsyncSession, gone: Source, kept: Source) -> None:
    check(gone, kept)
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
    theirs = aliased(SourceCredit)
    await session.execute(
        delete(SourceCredit).where(
            SourceCredit.source_id == gone.id,
            exists().where(
                theirs.source_id == kept.id,
                theirs.author_id == SourceCredit.author_id,
                theirs.role == SourceCredit.role,
            ),
        )
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
    tagged = select(SourceTag.tag_id).where(SourceTag.source_id == kept.id)
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
            note=f"The book was merged into “{kept.title}”; suggest the change there.",
            decided_at=func.now(),
        )
    )
    # Kept with the book that stays, so their contributors still see them.
    await session.execute(
        update(Proposal).where(Proposal.source_id == gone.id).values(source_id=kept.id)
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
