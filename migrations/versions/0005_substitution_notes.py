"""Substitution notes: an optional free-text amount ("3 tablespoons per egg").

Downgrade refuses while any note exists, rather than drop it.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("substitutions", sa.Column("note", sa.Text()))
    op.create_check_constraint("ck_substitutions_note_not_empty", "substitutions", "note <> ''")


def downgrade() -> None:
    kept = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM substitutions WHERE note IS NOT NULL"))
        .scalar_one()
    )
    if kept:
        raise RuntimeError(
            f"{kept} substitution note(s) exist, and the previous schema has nowhere to keep"
            " them. Remove them first if losing them is intended."
        )
    op.drop_column("substitutions", "note")
