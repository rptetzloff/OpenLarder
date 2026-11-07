"""Bulk import: reading the book list and recipe list, and storing recipes.

The browser drives an import in short steps, so no request runs long enough
to hit a proxy's timeout: it sends both CSV files here to be parsed, adds
each book through the ordinary add-by-ISBN route, then sends recipes in
batches. Nothing here stores the files themselves.

Bulk imports were to go through review; there is none yet, so an admin's
import publishes at once and anything doubtful is flagged on its recipe
instead. *Ray, 2026-11-07.* An import can be run again: a recipe already
there, by book, title and page, is skipped.

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

from openlarder import isbn, recipes
from openlarder.models import Edition, FlagKind, Recipe, RecipeFlag, RecipePage

BOOK_COLUMNS = ("Source Title", "Author(s)", "ISBN", "Year Published")
RECIPE_COLUMNS = ("Source", "Recipe Name", "Pg #", "Ingredients")
MAX_BATCH = 250

# What is left of a page reference split at a semicolon: "269)", "p. 42)".
_FRAGMENT = re.compile(r"^\(?\s*(?:pp?\.?|pg\.?)?\s*[\dixvlc]+\s*\)$", re.IGNORECASE)


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
    for line in (x for x in lines if x):
        if _FRAGMENT.match(line):
            flags.append((FlagKind.LINE_FRAGMENT, line))
        elif recipes.AMOUNT.match(line):
            flags.append((FlagKind.LINE_REMOVED, f"{line}: has an amount"))
        elif len(line) > recipes.MAX_LINE:
            flags.append((FlagKind.LINE_REMOVED, f"{line[:60]}…: too long"))
        else:
            kept.append(line)
    entry = recipes.clean(title, [(edition_id, page)], kept)
    if not entry.lines:
        flags.append((FlagKind.NO_INGREDIENTS, None))
    if page is None:
        flags.append((FlagKind.NO_PAGE, None))
    return Prepared(entry=entry, flags=flags)


@dataclass
class Item:
    row: int
    work_id: uuid.UUID
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
            select(Edition.id).where(Edition.isbn13 == item.isbn13, Edition.work_id == item.work_id)
        )
    # A book without an ISBN has one edition, the one added with it.
    ids = (await session.scalars(select(Edition.id).where(Edition.work_id == item.work_id))).all()
    return ids[0] if len(ids) == 1 else None


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

        # Run again, an import skips what it already added: same book, title
        # and page in this edition.
        same_title = (
            await session.execute(
                select(Recipe.id, RecipePage.page)
                .join(RecipePage, RecipePage.recipe_id == Recipe.id)
                .where(
                    Recipe.work_id == item.work_id,
                    func.lower(Recipe.title) == entry.title.lower(),
                    RecipePage.edition_id == edition_id,
                )
            )
        ).all()
        if any(page == entry.pages[edition_id] for _, page in same_title):
            outcome.skipped += 1
            continue

        recipe = await recipes.create(session, item.work_id, entry)
        recipe.created_by = admin_id
        flags = list(prepared.flags)
        if same_title:
            others = ", ".join(sorted(p or "no page" for _, p in same_title))
            flags.append((FlagKind.DUPLICATE_TITLE, f"also on page {others}"))
        for kind, detail in flags:
            session.add(RecipeFlag(recipe_id=recipe.id, kind=kind.value, detail=detail))
            outcome.flags.append((item.row, recipe.id, kind.value, detail))
        outcome.created += 1
    await session.flush()
    return outcome
