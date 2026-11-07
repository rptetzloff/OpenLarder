"""Flags for page references that don't land where they say.

An ingredient line citing a page ("Basic Cauli-Rice (p. 269)") is linked
to the recipe it means (references.py). Two cases need a person: the name
is a recipe the book has on another page (reference_page), as the index's
rule for a wrong page says, and the book has no recipe on the cited page
at all (unknown_reference).

Downgrade refuses while any flag of the new kinds exists, rather than drop
them.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "'duplicate_title', 'no_ingredients', 'no_page', 'line_removed', 'line_fragment'"
NEW = OLD + ", 'reference_page', 'unknown_reference'"


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_recipe_flags_kind_known"), "recipe_flags", type_="check")
    op.create_check_constraint(
        op.f("ck_recipe_flags_kind_known"), "recipe_flags", f"kind IN ({kinds})"
    )


def upgrade() -> None:
    _kinds(NEW)


def downgrade() -> None:
    held = op.get_bind().scalar(
        text(
            "SELECT count(*) FROM recipe_flags"
            " WHERE kind IN ('reference_page', 'unknown_reference')"
        )
    )
    if held:
        raise RuntimeError(f"{held} reference flags exist; deal with them before downgrading.")
    _kinds(OLD)
