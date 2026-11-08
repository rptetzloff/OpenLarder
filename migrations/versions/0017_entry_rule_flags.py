"""Flags for lines the entry rules would change (issue #26).

An import keeps every line it can and flags what detector.py finds: a line
the rules leave out (salt, pepper, sugar or water, or something optional),
since it may be one of the exceptions, as usually_left_out; and a line with
an amount or prep in it, with the bare ingredient suggested, as
line_detail.

Downgrade refuses while any flag of the new kinds exists, rather than drop
them.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = (
    "'duplicate_title', 'no_ingredients', 'no_page', 'line_removed', 'line_fragment',"
    " 'reference_page', 'unknown_reference'"
)
NEW = OLD + ", 'usually_left_out', 'line_detail'"


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_recipe_flags_kind_known"), "recipe_flags", type_="check")
    op.create_check_constraint(
        op.f("ck_recipe_flags_kind_known"), "recipe_flags", f"kind IN ({kinds})"
    )


def upgrade() -> None:
    _kinds(NEW)


def downgrade() -> None:
    held = op.get_bind().scalar(
        text("SELECT count(*) FROM recipe_flags WHERE kind IN ('usually_left_out', 'line_detail')")
    )
    if held:
        raise RuntimeError(f"{held} entry-rule flags exist; deal with them before downgrading.")
    _kinds(OLD)
