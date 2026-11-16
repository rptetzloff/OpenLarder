"""A piece of equipment is in the list, or a recipe brought it in.

*Ray's equipment spec, 2026-11-15:* a name typed for a recipe that the
list doesn't have makes a new thing, by anyone who can make an ingredient
that way, and "goes through the same review". An ingredient a recipe
brings in is hidden from anyone who can't see a recipe using it
(visibility.py): one typed into a private family collection is nobody
else's to read, and one in a contributor's recipe waits with the recipe.

The same holds for equipment from here, and it needs one thing an
ingredient doesn't: most equipment is in the list because the list was
written (migration 0079) or a moderator added to it, not because a recipe
named it, and those are everyone's whatever needs them. A Dutch oven
doesn't vanish because the only recipe that lists one so far is private.
`listed` says which a row is. Everything there is so far is listed.

Revision ID: 0081
Revises: 0080
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0081"
down_revision: str | None = "0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "equipment",
        sa.Column("listed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("equipment", "listed")
