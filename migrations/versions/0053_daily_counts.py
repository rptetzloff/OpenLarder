"""Daily allowances in the database (daily.py).

Asking for a book and sending a report, signed out, are limited per address
a day. The counts were kept in memory, so a deploy started them again and a
second app process would have kept its own. Nothing to carry over: today's
counts start from nothing once.

Revision ID: 0053
Revises: 0052
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_counts",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("what", sa.Text(), nullable=False),
        sa.Column("caller", sa.Text(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "what <> '' AND caller <> ''", name=op.f("ck_daily_counts_names_not_empty")
        ),
        sa.CheckConstraint("n >= 1", name=op.f("ck_daily_counts_n_positive")),
        sa.PrimaryKeyConstraint("day", "what", "caller", name=op.f("pk_daily_counts")),
    )


def downgrade() -> None:
    op.drop_table("daily_counts")
