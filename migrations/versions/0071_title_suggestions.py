"""Suggestions about a book's title.

The Suggestions queue takes two more kinds (title_rules.py): 'title_case',
a title that looks to be in sentence case, with the title-cased one; and
'title_apostrophe', a title where an author's name looks to have lost its
apostrophe. Each names a source and the title proposed for it.

Revision ID: 0071
Revises: 0070
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0071"
down_revision: str | None = "0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = "kind IN ('merge', 'parent', 'line_fix', 'tag', 'allergen')"
AFTER = (
    "kind IN ('merge', 'parent', 'line_fix', 'tag', 'allergen', 'title_case', 'title_apostrophe')"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_suggestions_kind_known"), "suggestions", type_="check")
    op.create_check_constraint(op.f("ck_suggestions_kind_known"), "suggestions", AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM suggestions WHERE kind IN ('title_case', 'title_apostrophe')")
    op.drop_constraint(op.f("ck_suggestions_kind_known"), "suggestions", type_="check")
    op.create_check_constraint(op.f("ck_suggestions_kind_known"), "suggestions", BEFORE)
