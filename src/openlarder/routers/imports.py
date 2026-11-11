"""Bulk import, for admins: read the two lists, then store recipes in batches.

See importer.py for how an import runs and what it flags. Books are added
through /api/sources (by ISBN) and /api/sources/manual (without one).
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from openlarder import history, importer, isbn
from openlarder.agreement import require_agreement
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import ImportRun, ImportRunLine, Recipe, Source, User

router = APIRouter(prefix="/api/import", tags=["import"])
# What an import adds is the catalog's, under the agreement (agreement.py).
WRITES = [SameOrigin, Depends(require_agreement)]


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
    chapter: str | None = None


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
    source_id: uuid.UUID
    isbn13: str | None = None
    title: str
    page: str | None = None
    ingredients: list[str] = []
    chapter: str | None = Field(default=None, max_length=200)


class Batch(BaseModel):
    items: list[ItemIn] = Field(max_length=importer.MAX_BATCH)
    # The run to record this batch in (Import history); none for a batch
    # sent outside a run.
    run_id: uuid.UUID | None = None


class RunStart(BaseModel):
    books_in_list: int = Field(ge=0)
    recipes_in_file: int = Field(ge=0)
    untitled_rows: list[int] = []


class LineIn(BaseModel):
    row: int | None = None
    book: str = ""
    recipe: str = ""
    kind: Literal["not_imported", "book_not_added"]
    detail: str = ""


class Lines(BaseModel):
    lines: list[LineIn] = Field(max_length=1000)


class RunFinish(BaseModel):
    books_added: int = Field(ge=0)
    books_existing: int = Field(ge=0)
    books_failed: int = Field(ge=0)


class RunOut(BaseModel):
    id: uuid.UUID
    started_by: str | None
    started_at: datetime
    finished_at: datetime | None
    books_in_list: int
    recipes_in_file: int
    books_added: int
    books_existing: int
    books_failed: int
    recipes_created: int
    recipes_skipped: int
    recipes_not_imported: int
    flags_raised: int
    lines: int


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
            RecipeOut(
                row=r.row,
                source=r.source,
                title=r.title,
                page=r.page,
                ingredients=r.lines,
                chapter=r.chapter,
            )
            for r in rows
        ],
        blank_rows=parsed.blank,
        untitled_rows=parsed.untitled,
        unknown_sources=sorted({r.source for r in rows if r.source.casefold() not in known}),
    )


@router.post("/recipes", response_model=BatchResult, dependencies=WRITES)
async def import_recipes(batch: Batch, admin: AdminUser, session: Session) -> BatchResult:
    await history.via(session, f"import:{batch.run_id}" if batch.run_id else "import")
    items = []
    for i in batch.items:
        try:
            isbn13 = isbn.normalise(i.isbn13) if i.isbn13 else None
        except isbn.InvalidIsbn as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        items.append(
            importer.Item(
                row=i.row,
                source_id=i.source_id,
                isbn13=isbn13,
                title=i.title,
                page=i.page,
                lines=i.ingredients,
                chapter=i.chapter,
            )
        )
    run = await _open_run(session, batch.run_id) if batch.run_id else None
    outcome = await importer.import_batch(session, admin.id, items)
    if run is not None:
        importer.record_batch(session, run, items, outcome)
    await session.commit()
    return BatchResult(
        created=outcome.created,
        skipped=outcome.skipped,
        errors=[ErrorOut(row=r, reason=why) for r, why in outcome.errors],
        flags=[FlagOut(row=r, recipe_id=rid, kind=k, detail=d) for r, rid, k, d in outcome.flags],
    )


async def _open_run(session, run_id: uuid.UUID) -> ImportRun:
    run = await session.get(ImportRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such import run.")
    if run.finished_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That import run has finished.")
    return run


@router.post("/runs", status_code=status.HTTP_201_CREATED, dependencies=WRITES)
async def start_run(body: RunStart, admin: AdminUser, session: Session) -> dict[str, uuid.UUID]:
    run = await importer.start_run(
        session, admin.id, body.books_in_list, body.recipes_in_file, body.untitled_rows
    )
    await session.commit()
    return {"id": run.id}


@router.post("/runs/{run_id}/lines", dependencies=[SameOrigin])
async def add_lines(
    run_id: uuid.UUID, body: Lines, admin: AdminUser, session: Session
) -> dict[str, int]:
    """Report lines only the browser knows: books not added, recipes it couldn't place."""
    run = await _open_run(session, run_id)
    for line in body.lines:
        session.add(ImportRunLine(run_id=run.id, **line.model_dump()))
        if line.kind == "not_imported":
            run.recipes_not_imported += 1
    await session.commit()
    return {"added": len(body.lines)}


class TypoOut(BaseModel):
    recipe_id: uuid.UUID
    recipe: str
    book: str
    detail: str


class Finished(BaseModel):
    finished: bool
    # Names that look like typos, flagged once the run's recipes are in.
    typos: list[TypoOut] = []


@router.post("/runs/{run_id}/finish", response_model=Finished, dependencies=[SameOrigin])
async def finish_run(
    run_id: uuid.UUID, body: RunFinish, admin: AdminUser, session: Session
) -> Finished:
    await history.via(session, f"import:{run_id}")
    run = await _open_run(session, run_id)
    flagged = await importer.flag_typos(session, run)
    run.books_added, run.books_existing, run.books_failed = (
        body.books_added,
        body.books_existing,
        body.books_failed,
    )
    run.finished_at = func.now()
    await session.commit()
    return Finished(
        finished=True,
        typos=[
            TypoOut(recipe_id=t.recipe_id, recipe=t.recipe, book=t.book, detail=t.detail)
            for t in flagged
        ],
    )


@router.get("/runs", response_model=list[RunOut])
async def list_runs(admin: AdminUser, session: Session) -> list[RunOut]:
    line_counts = (
        select(ImportRunLine.run_id, func.count().label("n"))
        .group_by(ImportRunLine.run_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(ImportRun, User.display_name, line_counts.c.n)
            .outerjoin(User, User.id == ImportRun.started_by)
            .outerjoin(line_counts, line_counts.c.run_id == ImportRun.id)
            .order_by(ImportRun.started_at.desc())
        )
    ).all()
    return [
        RunOut(
            id=run.id,
            started_by=name,
            started_at=run.started_at,
            finished_at=run.finished_at,
            lines=n or 0,
            **{c: getattr(run, c) for c in importer.RUN_COUNTS},
        )
        for run, name, n in rows
    ]


@router.get("/runs/{run_id}/report.csv")
async def run_report(run_id: uuid.UUID, admin: AdminUser, session: Session) -> Response:
    run = await session.get(ImportRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such import run.")
    lines = (
        await session.scalars(
            select(ImportRunLine)
            .where(ImportRunLine.run_id == run_id)
            .order_by(ImportRunLine.row.nulls_first(), ImportRunLine.kind)
        )
    ).all()
    recipe_ids = [line.recipe_id for line in lines if line.recipe_id]
    books = (
        dict(
            (
                await session.execute(
                    select(Recipe.id, Source.title)
                    .join(Source, Source.id == Recipe.source_id)
                    .where(Recipe.id.in_(recipe_ids))
                )
            ).all()
        )
        if recipe_ids
        else {}
    )
    stamp = run.started_at.strftime("%Y-%m-%d-%H%M")
    return Response(
        importer.report_csv(list(lines), books),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="openlarder-import-{stamp}.csv"'},
    )
