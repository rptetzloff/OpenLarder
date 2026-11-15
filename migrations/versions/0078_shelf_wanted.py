"""A book on a shelf is one its owner has, or one they want.

*Ray, 2026-11-14:* "Want this book" is a second state of the shelf, beside
having the book. Every row there is so far is a book someone has, which is
the default. A wanted book has no edition: which one is owned is said when
it is.

Revision ID: 0078
Revises: 0077
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0078"
down_revision: str | None = "0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shelf_books", sa.Column("state", sa.Text(), server_default="have", nullable=False)
    )
    op.create_check_constraint(
        op.f("ck_shelf_books_state_known"), "shelf_books", "state IN ('have', 'want')"
    )
    op.create_check_constraint(
        op.f("ck_shelf_books_wanted_has_no_edition"),
        "shelf_books",
        "state = 'have' OR edition_id IS NULL",
    )


def downgrade() -> None:
    # The books people want aren't ones they have: they go, so that what's
    # left means what it did.
    op.execute("DELETE FROM shelf_books WHERE state = 'want'")
    op.drop_constraint(op.f("ck_shelf_books_wanted_has_no_edition"), "shelf_books", type_="check")
    op.drop_constraint(op.f("ck_shelf_books_state_known"), "shelf_books", type_="check")
    op.drop_column("shelf_books", "state")
