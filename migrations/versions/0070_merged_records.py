"""Where a merged ingredient or author went.

Merging two ingredients, or two records of one author, deletes one and
moves everything to the other. Nothing said which went where, so the page
of the one that went became a 404 (pages.py): a bookmark, a link from
another site and a search engine's entry all led nowhere. A book's merge
has had its own record since 0058, with what it needs to be undone; these
two can't be undone, so their record is only the two ids.

Not a key to the one kept: if that's merged on into a third, this row
stays and is followed on. If it's deleted, the address is a 404 again.

Revision ID: 0070
Revises: 0069
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0070"
down_revision: str | None = "0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "merged_records",
        sa.Column("gone_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("kept_id", sa.UUID(), nullable=False),
        sa.Column(
            "merged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('ingredient', 'author')", name=op.f("ck_merged_records_kind_known")
        ),
        sa.CheckConstraint("gone_id <> kept_id", name=op.f("ck_merged_records_not_into_itself")),
        sa.PrimaryKeyConstraint("gone_id", name=op.f("pk_merged_records")),
    )
    op.create_index(op.f("ix_merged_records_kept_id"), "merged_records", ["kept_id"])


def downgrade() -> None:
    op.drop_table("merged_records")
