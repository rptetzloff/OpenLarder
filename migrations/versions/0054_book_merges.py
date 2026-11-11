"""A record of each merge of two books, so an administrator can unmerge it
(book_merge.py). *Ray, 2026-11-11: a check on moderators.*

Merges made before this have no record and can't be unmerged.

Revision ID: 0054
Revises: 0053
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "book_merges",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("gone_id", sa.UUID(), nullable=False),
        sa.Column("gone_title", sa.Text(), nullable=False),
        sa.Column("kept_id", sa.UUID(), nullable=False),
        sa.Column("merged_by", sa.UUID(), nullable=True),
        sa.Column(
            "merged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("saved", postgresql.JSONB(), nullable=False),
        sa.Column("undone_by", sa.UUID(), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("gone_title <> ''", name=op.f("ck_book_merges_gone_title_not_empty")),
        sa.ForeignKeyConstraint(
            ["merged_by"],
            ["users.id"],
            name=op.f("fk_book_merges_merged_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["undone_by"],
            ["users.id"],
            name=op.f("fk_book_merges_undone_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_book_merges")),
    )
    op.create_index(op.f("ix_book_merges_gone_id"), "book_merges", ["gone_id"])
    op.create_index(op.f("ix_book_merges_kept_id"), "book_merges", ["kept_id"])
    op.create_index("ix_book_merges_merged_at", "book_merges", ["merged_at"])


def downgrade() -> None:
    op.drop_table("book_merges")
