"""Bulk import: reading the book list and recipe list, and storing recipes.

The browser drives an import in short steps, so no request runs long enough
to hit a proxy's timeout: it sends both CSV files here to be parsed, adds
each book through the ordinary add-by-ISBN route, then sends recipes in
batches. Nothing here stores the files themselves.

Bulk imports were to go through review; there is none yet, so an admin's
import publishes at once and anything doubtful is flagged on its recipe
instead. *Ray, 2026-11-07.* An import can be run again: a row matching a
recipe already there in book, title, page and ingredients is skipped.
Anything less is a different recipe, imported and flagged if its title is
repeated: a book can print two recipes of one name, even on one page.
*Ray, 2026-11-07: "nothing wrong with flagging them as confirmation, but
not drop them".*

The column names are the household index's (an Apple Numbers export). The
Tag column is not imported for now. *Ray, 2026-11-07: tags to come later.*
"""

import csv
import io
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import detector, isbn, recipes, references
from openlarder.models import (
    Edition,
    FlagKind,
    ImportRun,
    ImportRunLine,
    Recipe,
    RecipeFlag,
    RecipeIngredient,
    RecipeLocation,
)

BOOK_COLUMNS = ("Source Title", "Author(s)", "ISBN", "Year Published")
RECIPE_COLUMNS = ("Source", "Recipe Name", "Pg #", "Ingredients")
MAX_BATCH = 250

# What is left of a page reference split at a semicolon: "269)", "p. 42)".
_FRAGMENT = re.compile(r"^\(?\s*(?:pp?\.?|pg\.?)?\s*[\dixvlc]+\s*\)$", re.IGNORECASE)
# "Chicken Bone Broth (p; 42)": a semicolon typed for the full stop, which
# splits the line at the page reference. The head ends in an open "(p" and
# the tail is the bare number.
_OPEN_PAGE = re.compile(r"\((pp?|pg)\.?\s*$", re.IGNORECASE)
_PAGE_TAIL = re.compile(r"^\s*([\dixvlc]+)\s*\)$", re.IGNORECASE)


def _rejoin(lines: list[str]) -> list[str]:
    """Put a page reference split by a stray semicolon back together."""
    joined: list[str] = []
    for line in lines:
        tail = _PAGE_TAIL.match(line)
        if tail and joined and _OPEN_PAGE.search(joined[-1]):
            head = _OPEN_PAGE.sub(lambda m: f"({m.group(1)}. ", joined[-1])
            joined[-1] = f"{head}{tail.group(1)})"
        else:
            joined.append(line)
    return joined


class UnreadableFile(ValueError):
    """The file can't be read as the expected list; the reason says why."""


@dataclass
class BookRow:
    source_title: str
    authors: list[str]
    isbn13: str | None
    year: int | None


@dataclass
class RecipeRow:
    row: int  # the line in the file, counting the header as 1
    source: str
    title: str
    page: str | None
    lines: list[str]


@dataclass
class Prepared:
    entry: recipes.RecipeEntry
    flags: list[tuple[FlagKind, str | None]] = field(default_factory=list)


def _read(text: str, columns: tuple[str, ...], what: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [c for c in columns if c not in (reader.fieldnames or [])]
    if missing:
        raise UnreadableFile(f"The {what} has no {', '.join(missing)} column.")
    return list(reader)


def _squash(text: str | None) -> str:
    return " ".join((text or "").split())


def parse_books(text: str) -> list[BookRow]:
    books = []
    for number, line in enumerate(_read(text, BOOK_COLUMNS, "book list"), start=2):
        title = _squash(line["Source Title"])
        if not title:
            continue
        raw_isbn = _squash(line["ISBN"])
        try:
            isbn13 = isbn.normalise(raw_isbn) if raw_isbn else None
        except isbn.InvalidIsbn as exc:
            raise UnreadableFile(f"Row {number} of the book list ({title}): {exc}") from None
        year = _squash(line["Year Published"])
        books.append(
            BookRow(
                source_title=title,
                # Commas separate co-authors in the book list.
                authors=[a for a in (_squash(x) for x in line["Author(s)"].split(",")) if a],
                isbn13=isbn13,
                year=int(year) if year.isdigit() else None,
            )
        )
    return books


@dataclass
class ParsedRecipes:
    rows: list[RecipeRow]
    blank: int  # entirely blank rows, skipped
    # Rows with something in them but no title or no book, which can't be
    # placed: the household index has 31 ingredient lists alone on a row.
    untitled: list[int]


def parse_recipes(text: str) -> ParsedRecipes:
    rows, blank, untitled = [], 0, []
    for number, line in enumerate(_read(text, RECIPE_COLUMNS, "recipe list"), start=2):
        if not any(_squash(v) for v in line.values() if isinstance(v, str)):
            blank += 1
            continue
        if not _squash(line["Recipe Name"]) or not _squash(line["Source"]):
            untitled.append(number)
            continue
        rows.append(
            RecipeRow(
                row=number,
                source=_squash(line["Source"]),
                title=_squash(line["Recipe Name"]),
                page=_squash(line["Pg #"]) or None,
                lines=[_squash(x) for x in (line["Ingredients"] or "").split(";")],
            )
        )
    return ParsedRecipes(rows=rows, blank=blank, untitled=untitled)


def prepare(title: str, edition_id: uuid.UUID, page: str | None, lines: list[str]) -> Prepared:
    """Apply the entry rules to one imported row, flagging what they remove.

    Raises recipes.InvalidRecipe only for what makes the row unusable (no
    title); a bad line is dropped and flagged, not fatal, because the rest
    of the recipe is still worth having.
    """
    flags: list[tuple[FlagKind, str | None]] = []
    kept = []
    for line in _rejoin([x for x in lines if x]):
        if _FRAGMENT.match(line):
            flags.append((FlagKind.LINE_FRAGMENT, line))
        elif recipes.AMOUNT.match(line):
            flags.append((FlagKind.LINE_REMOVED, f"{line}: has an amount"))
        elif len(line) > recipes.MAX_LINE:
            flags.append((FlagKind.LINE_REMOVED, f"{line[:60]}…: too long"))
        else:
            kept.append(line)
            # Kept and flagged: the line alone can't say if it's an exception.
            found = detector.review(line)
            if found.remove:
                flags.append((FlagKind.USUALLY_LEFT_OUT, line))
            elif found.suggestion:
                flags.append((FlagKind.LINE_DETAIL, f"{line} → {found.suggestion}"))
    entry = recipes.clean(title, [(edition_id, page)], kept)
    if not entry.lines:
        flags.append((FlagKind.NO_INGREDIENTS, None))
    if page is None:
        flags.append((FlagKind.NO_PAGE, None))
    return Prepared(entry=entry, flags=flags)


@dataclass
class Item:
    row: int
    source_id: uuid.UUID
    isbn13: str | None
    title: str
    page: str | None
    lines: list[str]


@dataclass
class Outcome:
    created: int = 0
    skipped: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)
    # (row, recipe ID, kind, detail) for every flag raised
    flags: list[tuple[int, uuid.UUID, str, str | None]] = field(default_factory=list)


async def _edition(session: AsyncSession, item: Item) -> uuid.UUID | None:
    if item.isbn13:
        return await session.scalar(
            select(Edition.id).where(
                Edition.isbn13 == item.isbn13, Edition.source_id == item.source_id
            )
        )
    # A book without an ISBN has one edition, the one added with it.
    ids = (
        await session.scalars(select(Edition.id).where(Edition.source_id == item.source_id))
    ).all()
    return ids[0] if len(ids) == 1 else None


async def _ingredients(session: AsyncSession, recipe_ids: list[uuid.UUID]) -> list[list[str]]:
    """Each recipe's ingredient lines, in order."""
    lines: dict[uuid.UUID, list[str]] = {r: [] for r in recipe_ids}
    for recipe_id, text in (
        await session.execute(
            select(RecipeIngredient.recipe_id, RecipeIngredient.original_text)
            .where(RecipeIngredient.recipe_id.in_(recipe_ids))
            .order_by(RecipeIngredient.recipe_id, RecipeIngredient.position)
        )
    ).all():
        lines[recipe_id].append(text)
    return list(lines.values())


async def import_batch(session: AsyncSession, admin_id: uuid.UUID, items: list[Item]) -> Outcome:
    outcome = Outcome()
    for item in items:
        edition_id = await _edition(session, item)
        if edition_id is None:
            outcome.errors.append((item.row, "Its book isn't in the catalog yet."))
            continue
        try:
            prepared = prepare(item.title, edition_id, item.page, item.lines)
        except recipes.InvalidRecipe as exc:
            outcome.errors.append((item.row, str(exc)))
            continue
        entry = prepared.entry

        # Run again, an import skips what it already added: same book, title,
        # page in this edition and ingredients. A repeated title alone is
        # another recipe, kept and flagged.
        same_title = (
            await session.execute(
                select(Recipe.id, RecipeLocation.page)
                .join(RecipeLocation, RecipeLocation.recipe_id == Recipe.id)
                .where(
                    Recipe.source_id == item.source_id,
                    func.lower(Recipe.title) == entry.title.lower(),
                    RecipeLocation.edition_id == edition_id,
                )
            )
        ).all()
        same_page = [rid for rid, page in same_title if page == entry.pages[edition_id]]
        if same_page and entry.lines in await _ingredients(session, same_page):
            outcome.skipped += 1
            continue

        recipe = await recipes.create(session, item.source_id, entry)
        recipe.created_by = admin_id
        flags = list(prepared.flags)
        if same_title:
            others = ", ".join(sorted({p or "no page" for _, p in same_title}))
            flags.append((FlagKind.DUPLICATE_TITLE, f"also on page {others}"))
        for kind, detail in flags:
            session.add(RecipeFlag(recipe_id=recipe.id, kind=kind.value, detail=detail))
            outcome.flags.append((item.row, recipe.id, kind.value, detail))
        outcome.created += 1
    await session.flush()
    # A batch can hold a recipe that earlier ones cited, so their whole books
    # are linked again, not just the new rows.
    for source_id in sorted({i.source_id for i in items}):
        await references.relink(session, source_id)
    return outcome


# Import history (migration 0013). A run is opened when an import starts,
# recorded batch by batch, and closed with the book totals at the end.

RUN_COUNTS = (
    "books_in_list",
    "recipes_in_file",
    "books_added",
    "books_existing",
    "books_failed",
    "recipes_created",
    "recipes_skipped",
    "recipes_not_imported",
    "flags_raised",
)

KIND_LABELS = {
    "not_imported": "Not imported",
    "book_not_added": "Book not added",
    **{k.value: k.value.replace("_", " ") for k in FlagKind},
}


async def start_run(
    session: AsyncSession, admin_id: uuid.UUID, books: int, recipes: int, untitled: list[int]
) -> ImportRun:
    run = ImportRun(started_by=admin_id, books_in_list=books, recipes_in_file=recipes)
    session.add(run)
    await session.flush()
    for row in untitled:
        session.add(
            ImportRunLine(
                run_id=run.id,
                row=row,
                kind="not_imported",
                detail="No title or no book on this row",
            )
        )
    run.recipes_not_imported = len(untitled)
    await session.flush()
    return run


def record_batch(
    session: AsyncSession, run: ImportRun, items: list[Item], outcome: Outcome
) -> None:
    """Add a batch's totals and report lines to its run."""
    titles = {i.row: i.title for i in items}
    run.recipes_created += outcome.created
    run.recipes_skipped += outcome.skipped
    run.recipes_not_imported += len(outcome.errors)
    run.flags_raised += len(outcome.flags)
    for row, reason in outcome.errors:
        session.add(
            ImportRunLine(
                run_id=run.id,
                row=row,
                recipe=titles.get(row, ""),
                kind="not_imported",
                detail=reason,
            )
        )
    for row, recipe_id, kind, detail in outcome.flags:
        session.add(
            ImportRunLine(
                run_id=run.id,
                row=row,
                recipe=titles.get(row, ""),
                kind=kind,
                detail=detail or "",
                recipe_id=recipe_id,
            )
        )


def report_csv(lines: list[ImportRunLine], books: dict[uuid.UUID, str]) -> str:
    """A run's report as CSV, the same columns the import page offers."""
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(["Row", "Book", "Recipe", "What", "Detail"])
    for line in lines:
        book = line.book or (books.get(line.recipe_id, "") if line.recipe_id else "")
        writer.writerow(
            [
                "" if line.row is None else line.row,
                book,
                line.recipe,
                KIND_LABELS.get(line.kind, line.kind),
                line.detail,
            ]
        )
    return out.getvalue()
