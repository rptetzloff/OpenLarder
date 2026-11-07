"""Bulk import, for admins: read the two lists, then store recipes in batches.

See importer.py for how an import runs and what it flags. Books are added
through /api/books (by ISBN) and /api/books/manual (without one).
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from openlarder import importer, isbn
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session

router = APIRouter(prefix="/api/import", tags=["import"])


class Files(BaseModel):
    books_csv: str
    recipes_csv: str


class BookOut(BaseModel):
    source_title: str
    authors: list[str]
    isbn13: str | None
    year: int | None
    recipes: int


class RecipeOut(BaseModel):
    row: int
    source: str
    title: str
    page: str | None
    ingredients: list[str]


class Parsed(BaseModel):
    books: list[BookOut]
    recipes: list[RecipeOut]
    blank_rows: int
    # Rows with no title or no book, by row number in the file.
    untitled_rows: list[int]
    # Recipe rows naming a book that isn't in the book list.
    unknown_sources: list[str]


class ItemIn(BaseModel):
    row: int
    work_id: uuid.UUID
    isbn13: str | None = None
    title: str
    page: str | None = None
    ingredients: list[str] = []


class Batch(BaseModel):
    items: list[ItemIn] = Field(max_length=importer.MAX_BATCH)


class FlagOut(BaseModel):
    row: int
    recipe_id: uuid.UUID
    kind: str
    detail: str | None


class ErrorOut(BaseModel):
    row: int
    reason: str


class BatchResult(BaseModel):
    created: int
    skipped: int
    errors: list[ErrorOut]
    flags: list[FlagOut]


@router.post("/parse", response_model=Parsed, dependencies=[SameOrigin])
async def parse(files: Files, admin: AdminUser) -> Parsed:
    try:
        books = importer.parse_books(files.books_csv)
        parsed = importer.parse_recipes(files.recipes_csv)
    except importer.UnreadableFile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    known = {b.source_title.casefold() for b in books}
    rows = parsed.rows
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.source.casefold()] = counts.get(r.source.casefold(), 0) + 1
    return Parsed(
        books=[
            BookOut(
                source_title=b.source_title,
                authors=b.authors,
                isbn13=b.isbn13,
                year=b.year,
                recipes=counts.get(b.source_title.casefold(), 0),
            )
            for b in books
        ],
        recipes=[
            RecipeOut(row=r.row, source=r.source, title=r.title, page=r.page, ingredients=r.lines)
            for r in rows
        ],
        blank_rows=parsed.blank,
        untitled_rows=parsed.untitled,
        unknown_sources=sorted({r.source for r in rows if r.source.casefold() not in known}),
    )


@router.post("/recipes", response_model=BatchResult, dependencies=[SameOrigin])
async def import_recipes(batch: Batch, admin: AdminUser, session: Session) -> BatchResult:
    items = []
    for i in batch.items:
        try:
            isbn13 = isbn.normalise(i.isbn13) if i.isbn13 else None
        except isbn.InvalidIsbn as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        items.append(
            importer.Item(
                row=i.row,
                work_id=i.work_id,
                isbn13=isbn13,
                title=i.title,
                page=i.page,
                lines=i.ingredients,
            )
        )
    outcome = await importer.import_batch(session, admin.id, items)
    await session.commit()
    return BatchResult(
        created=outcome.created,
        skipped=outcome.skipped,
        errors=[ErrorOut(row=r, reason=why) for r, why in outcome.errors],
        flags=[FlagOut(row=r, recipe_id=rid, kind=k, detail=d) for r, rid, k, d in outcome.flags],
    )
