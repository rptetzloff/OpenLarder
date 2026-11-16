"""Flags for an import's equipment, as there are for its ingredients.

*Ray's equipment spec, 2026-11-15:* the import format gets an Equipment
field. *Ray, 2026-11-16:* equipment is treated as ingredients are. An
import keeps what it can of a row and flags the rest on its recipe, so:

- `equipment_removed`, beside `line_removed`: something in the Equipment
  column that saving refuses (what any kitchen has, a size alone) was left
  out. The detail is the sentence the form would have refused it with.
- `equipment_typo`, beside `possible_typo`: a recipe needs a thing that
  isn't in the equipment list and is spelt like one that is ("Wafle iron →
  Waffle iron"), for a person to change in one click or dismiss.

Downgrade refuses while any flag of the new kinds exists, rather than drop
them.

Revision ID: 0082
Revises: 0081
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0082"
down_revision: str | None = "0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = (
    "'duplicate_title', 'no_ingredients', 'no_page', 'line_removed', 'line_fragment',"
    " 'reference_page', 'unknown_reference', 'usually_left_out', 'line_detail',"
    " 'possible_typo'"
)
NEW = OLD + ", 'equipment_removed', 'equipment_typo'"


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_recipe_flags_kind_known"), "recipe_flags", type_="check")
    op.create_check_constraint(
        op.f("ck_recipe_flags_kind_known"), "recipe_flags", f"kind IN ({kinds})"
    )


def upgrade() -> None:
    _kinds(NEW)


def downgrade() -> None:
    if op.get_bind().scalar(
        text(
            "SELECT count(*) FROM recipe_flags"
            " WHERE kind IN ('equipment_removed', 'equipment_typo')"
        )
    ):
        raise RuntimeError("Equipment flags exist; deal with them before downgrading.")
    _kinds(OLD)
