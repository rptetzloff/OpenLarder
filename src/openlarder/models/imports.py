"""Import history: each bulk import run, its totals, and its report lines.

Admin data, not catalog data: not in the ODbL export. See importer.py for
how a run proceeds; the server records it batch by batch, so a run whose
browser closed halfway still shows what it did, with no finish time.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, uuid_pk

COUNTS = (
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


def _count() -> Mapped[int]:
    return mapped_column(Integer, nullable=False, server_default="0")


class ImportRun(Base):
    __tablename__ = "import_runs"
    __table_args__ = (
        CheckConstraint(" AND ".join(f"{c} >= 0" for c in COUNTS), name="counts_not_negative"),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at", name="finished_after_started"
        ),
        Index("ix_import_runs_started_at", "started_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Empty while running, and for good if the browser closed before the end.
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    books_in_list: Mapped[int] = _count()
    recipes_in_file: Mapped[int] = _count()
    books_added: Mapped[int] = _count()
    books_existing: Mapped[int] = _count()
    books_failed: Mapped[int] = _count()
    recipes_created: Mapped[int] = _count()
    recipes_skipped: Mapped[int] = _count()
    recipes_not_imported: Mapped[int] = _count()
    flags_raised: Mapped[int] = _count()


class ImportRunLine(Base):
    """One line of a run's report: a recipe not imported, a book not added, a flag."""

    __tablename__ = "import_run_lines"
    __table_args__ = (
        CheckConstraint("kind <> ''", name="kind_not_empty"),
        Index("ix_import_run_lines_run_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_runs.id", ondelete="CASCADE"), nullable=False
    )
    # The row in the recipe list, where there is one.
    row: Mapped[int | None] = mapped_column(Integer)
    book: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    recipe: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # The recipe a flag is on; null once the recipe is removed.
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.id", ondelete="SET NULL")
    )
