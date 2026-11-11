"""Undoing a change from the edit history (migration 0040). *SCOPING.md:
full edit history on every record, one-click revert.*

A change is every row one save added, changed or removed. Undoing it puts
each back as it was: added rows go (children before parents), so a line
saved in a removed one's place makes room for it; removed rows return
(parents before children); changed columns get their old values. The
undo is itself a change, through "revert:<change>", so it can be undone in
turn.

It's refused when something has changed one of those rows since, as undoing
it would silently throw that later work away; that one is undone first, or
the row fixed by hand. A removal recorded before migration 0042 lacks the
columns needed to put it back, and is refused too.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Table, and_, delete, func, insert, select, tuple_, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import history
from openlarder.models import Base, Revision

# Parents before children: the order removed rows are put back in, and the
# reverse of the order added rows are taken away in.
ORDER = [
    "authors",
    "ingredients",
    "tags",
    "sources",
    "author_links",
    "ingredient_aliases",
    "ingredient_allergens",
    "editions",
    "issues",
    "episodes",
    "web_pages",
    "source_credits",
    "source_tags",
    "purchase_links",
    "recipes",
    "recipe_locations",
    "recipe_ingredients",
    "ingredient_options",
    "recipe_tags",
    "substitutions",
]


# Required columns a removal before migration 0042 didn't keep.
KEYS = {"ingredients": "match_key", "ingredient_aliases": "match_key", "authors": "name_key"}


class CantRevert(Exception):
    """Why, in words to show beside the button."""


def _value(table: Table, column: str, raw):
    """A value as the revision's JSON has it, as its column takes it."""
    if raw is None:
        return None
    try:
        kind = table.c[column].type.python_type
    except NotImplementedError:
        return raw
    if kind is uuid.UUID:
        return uuid.UUID(raw)
    if kind is datetime:
        return datetime.fromisoformat(raw)
    if kind is date:
        return date.fromisoformat(raw)
    return raw


def _row(table: Table, changes: dict, side: int) -> dict:
    return {
        c: _value(table, c, values[side])
        for c, values in changes.items()
        if c in table.c and values[side] is not None
    }


def _where(table: Table, revision: Revision, values: dict):
    """The row a revision is of: by id, or (a tag on a recipe or source,
    which has none) by every column."""
    if "id" in table.c and revision.record_id is not None:
        return table.c.id == revision.record_id
    return and_(*(table.c[c] == v for c, v in values.items()))


async def later_changes(session: AsyncSession, revisions: list[Revision]) -> int:
    """How many changes since this one touched the same rows."""
    last = max(r.id for r in revisions)
    rows = [(r.table_name, r.record_id) for r in revisions if r.record_id is not None]
    if not rows:
        return 0
    later = await session.scalar(
        select(func.count(func.distinct(Revision.change_id))).where(
            Revision.id > last,
            Revision.change_id != revisions[0].change_id,
            tuple_(Revision.table_name, Revision.record_id).in_(rows),
        )
    )
    return later or 0


async def revert(session: AsyncSession, change_id: uuid.UUID) -> int:
    """Undo the change; how many rows it put back, changed back or took away."""
    revisions = list(
        await session.scalars(
            select(Revision).where(Revision.change_id == change_id).order_by(Revision.id)
        )
    )
    if not revisions:
        raise CantRevert("There's no such change.")
    via = revisions[0].via or ""
    if via.startswith("merge:"):
        raise CantRevert(
            "A merge of two books is taken apart by unmerging it, which an administrator"
            " can do from Merged books."
        )
    if via.startswith("unmerge:"):
        raise CantRevert("An unmerge is undone by merging the two books again.")
    if n := await later_changes(session, revisions):
        raise CantRevert(
            f"{n} later {'change touches' if n == 1 else 'changes touch'} the same records."
            " Undo those first, or fix it by hand."
        )
    tables = Base.metadata.tables
    rank = {name: i for i, name in enumerate(ORDER)}
    for r in revisions:
        if r.table_name not in tables or r.table_name not in rank:
            raise CantRevert(f"Changes to {r.table_name} can't be undone here.")
    for r in revisions:
        if r.action == "d" and r.table_name in KEYS and KEYS[r.table_name] not in r.changes:
            raise CantRevert(
                "It removed something before removals were kept whole, so it can't be put back."
            )
    await history.via(session, f"revert:{change_id}")
    done = 0
    try:
        async with session.begin_nested():
            # Added rows away, children first.
            for r in sorted(
                (r for r in revisions if r.action == "i"),
                key=lambda r: (-rank[r.table_name], -r.id),
            ):
                table = tables[r.table_name]
                await session.execute(
                    delete(table).where(_where(table, r, _row(table, r.changes, 1)))
                )
                done += 1
            # Removed rows back, parents first.
            for r in sorted(
                (r for r in revisions if r.action == "d"), key=lambda r: (rank[r.table_name], r.id)
            ):
                table = tables[r.table_name]
                await session.execute(insert(table).values(**_row(table, r.changes, 0)))
                done += 1
            # Changed columns back, newest first.
            for r in reversed([r for r in revisions if r.action == "u"]):
                table = tables[r.table_name]
                values = {c: _value(table, c, b) for c, (b, _) in r.changes.items() if c in table.c}
                await session.execute(
                    update(table)
                    .where(_where(table, r, _row(table, r.changes, 1)))
                    .values(**values)
                )
                done += 1
    except IntegrityError as exc:
        raise CantRevert(
            "It can't be undone as it stands: something it relied on has changed or gone."
        ) from exc
    except DBAPIError as exc:
        raise CantRevert("It can't be undone as it stands.") from exc
    return done
