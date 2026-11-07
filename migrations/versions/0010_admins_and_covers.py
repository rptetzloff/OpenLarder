"""Admins, who may add books, and Open Library cover IDs on editions.

Until there is a review queue, edit history and the ODbL agreement, only an
admin can add to the catalog, so books publish at once without leaving a
history of a structure that is still changing. *Decided by Ray, 2026-11-07.*
Nobody is an admin by default; the first is set by hand in the database.

An edition's cover is shown from Open Library by its cover ID, not copied.
cover_key stays for when covers are stored.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.add_column("editions", sa.Column("open_library_cover_id", sa.Integer()))
    op.create_check_constraint(
        op.f("ck_editions_open_library_cover_id_positive"),
        "editions",
        "open_library_cover_id > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_editions_open_library_cover_id_positive"), "editions", type_="check"
    )
    op.drop_column("editions", "open_library_cover_id")
    op.drop_column("users", "is_admin")
