"""Flags for names that look like typos (typos.py).

*Ray, 2026-11-10: flag everything.* An import flags each public recipe using
a rare ingredient name close to a much commoner one ("Lemon Jucie → Lemon
Juice"), for a person to change in one click or dismiss.

Downgrade refuses while any flag of the new kind exists, rather than drop
them.

Revision ID: 0052
Revises: 0051
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = (
    "'duplicate_title', 'no_ingredients', 'no_page', 'line_removed', 'line_fragment',"
    " 'reference_page', 'unknown_reference', 'usually_left_out', 'line_detail'"
)
NEW = OLD + ", 'possible_typo'"


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_recipe_flags_kind_known"), "recipe_flags", type_="check")
    op.create_check_constraint(
        op.f("ck_recipe_flags_kind_known"), "recipe_flags", f"kind IN ({kinds})"
    )


def upgrade() -> None:
    _kinds(NEW)


def downgrade() -> None:
    if op.get_bind().scalar(text("SELECT count(*) FROM recipe_flags WHERE kind = 'possible_typo'")):
        raise RuntimeError("Possible-typo flags exist; deal with them before downgrading.")
    _kinds(OLD)
