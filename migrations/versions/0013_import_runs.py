"""Import history: each bulk import run, its totals, and its report lines.

A run is recorded as it goes, by the server, so the history survives a
browser closed halfway: totals and lines up to the last batch are kept, and
finished_at stays empty. Lines are what the report lists: recipes not
imported and why, books not added, and every flag raised. *Ray, 2026-11-07:
"there probably needs to be a logging of imports and results".*

Downgrade refuses while any run exists, rather than drop the history.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
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


def upgrade() -> None:
    op.create_table(
        "import_runs",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("started_by", UUID),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *[sa.Column(c, sa.Integer(), server_default="0", nullable=False) for c in COUNTS],
        sa.PrimaryKeyConstraint("id", name="pk_import_runs"),
        sa.ForeignKeyConstraint(
            ["started_by"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_import_runs_started_by_users",
        ),
        sa.CheckConstraint(
            " AND ".join(f"{c} >= 0" for c in COUNTS),
            name=op.f("ck_import_runs_counts_not_negative"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_import_runs_finished_after_started"),
        ),
    )
    op.create_index("ix_import_runs_started_at", "import_runs", ["started_at"])

    op.create_table(
        "import_run_lines",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("row", sa.Integer()),
        sa.Column("book", sa.Text(), server_default="", nullable=False),
        sa.Column("recipe", sa.Text(), server_default="", nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        sa.Column("recipe_id", UUID),
        sa.PrimaryKeyConstraint("id", name="pk_import_run_lines"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["import_runs.id"],
            ondelete="CASCADE",
            name="fk_import_run_lines_run_id_import_runs",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            ondelete="SET NULL",
            name="fk_import_run_lines_recipe_id_recipes",
        ),
        sa.CheckConstraint("kind <> ''", name=op.f("ck_import_run_lines_kind_not_empty")),
    )
    op.create_index("ix_import_run_lines_run_id", "import_run_lines", ["run_id"])


def downgrade() -> None:
    kept = op.get_bind().execute(sa.text("SELECT count(*) FROM import_runs")).scalar_one()
    if kept:
        raise RuntimeError(
            f"{kept} import run(s) are recorded, and the previous schema has nowhere to keep"
            " them. Remove them first if losing the history is intended."
        )
    op.drop_table("import_run_lines")
    op.drop_table("import_runs")
