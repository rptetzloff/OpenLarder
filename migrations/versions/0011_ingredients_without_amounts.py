"""Ingredient lines name the ingredient only: no amount, unit, form or prep.

OpenLarder is a reference to what is in cookbooks, not a recipe site. An
ingredient line says what goes in ("rhubarb"), so a recipe can be found by
it; how much, and what to do with it, stay in the book. *Decided by Ray,
2026-11-07, superseding "the option carries its own quantity" (2026-11-06).*
Form ("canned") is part of what the ingredient is, so it belongs to the
canonical ingredient ("canned tomatoes"), not to a column; prep ("diced") is
method. *Dropping form and prep too is Claude's reading of the same
decision.*

Upgrade refuses while any of these columns holds a value, rather than drop
it. None should: nothing ever wrote them.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DROPPED = {
    "recipe_ingredients": ("quantity", "unit", "form", "prep"),
    "ingredient_options": ("quantity", "unit"),
}


def upgrade() -> None:
    bind = op.get_bind()
    for table, columns in DROPPED.items():
        held = " OR ".join(f"{c} IS NOT NULL" for c in columns)
        count = bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE {held}")).scalar_one()
        if count:
            raise RuntimeError(
                f"{count} row(s) in {table} hold an amount, unit, form or prep. Look at them"
                " before dropping: OpenLarder no longer stores these."
            )
    for table, columns in DROPPED.items():
        for column in columns:
            op.drop_column(table, column)


def downgrade() -> None:
    for table, columns in DROPPED.items():
        for column in columns:
            op.add_column(table, sa.Column(column, sa.Text()))
