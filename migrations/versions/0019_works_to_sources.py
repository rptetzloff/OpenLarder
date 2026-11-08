"""Books become sources: a recipe's source can be any kind of thing.

*Ray, 2026-11-08: "a source could be a book or a blog or an instagram post
or a tv episode or a magazine article".* A work becomes a source with a
kind; books are the only kind so far. Each kind keeps its own parts in its
own table: a book's are its editions, which keep that name, and later
kinds add theirs (a magazine's issues, a show's episodes, a site's posts).
Where a recipe is in its source is its location: a page in an edition for
a book, later a time or an address. So recipe_pages becomes
recipe_locations, and work_id becomes source_id wherever it appears.

Constraint, index and trigger names follow the tables and columns, so they
still match what the models' naming convention gives. Views follow by
themselves: Postgres keeps them by reference, not by name.

Downgrade refuses while any source isn't a book, rather than drop it.

Revision ID: 0019
Revises: 0018
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = {
    "works": "sources",
    "work_credits": "source_credits",
    "work_tags": "source_tags",
    "recipe_pages": "recipe_locations",
}
# Tables with a work_id column, by their names after the rename.
WITH_WORK_ID = (
    "source_credits",
    "source_tags",
    "recipe_locations",
    "editions",
    "recipes",
)
# Tables whose constraint, index or trigger names can mention the old names.
NAMED = (*TABLES.values(), "editions", "recipes")


def _forward(name: str) -> str:
    # Not inside open_library_work_id, which is Open Library's term.
    name = re.sub(r"(?<!library)_work_id", "_source_id", name)
    for old, new in TABLES.items():
        name = re.sub(rf"(^|_){old}(?=_|$)", rf"\g<1>{new}", name)
    return name


def _backward(name: str) -> str:
    name = re.sub(r"_source_id", "_work_id", name)
    for old, new in TABLES.items():
        name = re.sub(rf"(^|_){new}(?=_|$)", rf"\g<1>{old}", name)
    return name


def _rename_names(tables: Sequence[str], rename) -> None:
    bind = op.get_bind()
    for table in tables:
        constraints = bind.execute(
            sa.text(
                "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid"
                " WHERE t.relname = :t"
            ),
            {"t": table},
        ).scalars()
        for name in list(constraints):
            if (new := rename(name)) != name:
                op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{name}" TO "{new}"')
        # Indexes left: those not behind a constraint, renamed above with it.
        indexes = bind.execute(
            sa.text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": table}
        ).scalars()
        for name in list(indexes):
            if (new := rename(name)) != name:
                op.execute(f'ALTER INDEX "{name}" RENAME TO "{new}"')
        triggers = bind.execute(
            sa.text(
                "SELECT tgname FROM pg_trigger g JOIN pg_class t ON t.oid = g.tgrelid"
                " WHERE t.relname = :t AND NOT g.tgisinternal"
            ),
            {"t": table},
        ).scalars()
        for name in list(triggers):
            if (new := rename(name)) != name:
                op.execute(f'ALTER TRIGGER "{name}" ON "{table}" RENAME TO "{new}"')


def upgrade() -> None:
    for old, new in TABLES.items():
        op.rename_table(old, new)
    for table in WITH_WORK_ID:
        op.alter_column(table, "work_id", new_column_name="source_id")
    _rename_names(NAMED, _forward)
    op.add_column("sources", sa.Column("kind", sa.Text(), server_default="book", nullable=False))
    op.create_check_constraint(op.f("ck_sources_kind_known"), "sources", "kind IN ('book')")


def downgrade() -> None:
    others = op.get_bind().scalar(sa.text("SELECT count(*) FROM sources WHERE kind <> 'book'"))
    if others:
        raise RuntimeError(f"{others} sources aren't books; remove them before downgrading.")
    op.drop_constraint(op.f("ck_sources_kind_known"), "sources", type_="check")
    op.drop_column("sources", "kind")
    _rename_names(NAMED, _backward)
    for table in WITH_WORK_ID:
        op.alter_column(table, "source_id", new_column_name="work_id")
    for old, new in TABLES.items():
        op.rename_table(new, old)
