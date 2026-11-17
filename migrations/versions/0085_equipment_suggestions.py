"""Suggestions of equipment a recipe needs.

The Suggestions queue takes one more kind (equipment_rules.py):
'equipment', a piece of equipment a recipe's title, tags or source say it
probably needs. It names a recipe and a piece of equipment. *Ray's
equipment spec, 2026-11-15.*

Downgrade deletes them, as 0071's deletes the title kinds: they're what a
rule made, and the rule makes them again.

Revision ID: 0085
Revises: 0084
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0085"
down_revision: str | None = "0084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = (
    "kind IN ('merge', 'parent', 'line_fix', 'tag', 'allergen', 'title_case', 'title_apostrophe')"
)
AFTER = (
    "kind IN ('merge', 'parent', 'line_fix', 'tag', 'allergen', 'title_case',"
    " 'title_apostrophe', 'equipment')"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_suggestions_kind_known"), "suggestions", type_="check")
    op.create_check_constraint(op.f("ck_suggestions_kind_known"), "suggestions", AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM suggestions WHERE kind = 'equipment'")
    op.drop_constraint(op.f("ck_suggestions_kind_known"), "suggestions", type_="check")
    op.create_check_constraint(op.f("ck_suggestions_kind_known"), "suggestions", BEFORE)
