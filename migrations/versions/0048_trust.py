"""Trusted contributors: what they add publishes without waiting for review.

*Ray, 2026-11-10:* earned after "the greater of 250 recipes or 5 books"
approved: at least 250 approved recipes, across at least 5 different
books (trust.py; both settings). A moderator can grant it by hand or
withhold it, and withholding sticks: it isn't earned back by itself.

Revision ID: 0048
Revises: 0047
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("trust", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("trust_set_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("trust_set_by", sa.UUID(), nullable=True))
    op.create_check_constraint(
        op.f("ck_users_trust_known"), "users", "trust IN ('earned', 'granted', 'withheld')"
    )
    op.create_foreign_key(
        op.f("fk_users_trust_set_by_users"),
        "users",
        "users",
        ["trust_set_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_users_trust_set_by_users"), "users", type_="foreignkey")
    op.drop_constraint(op.f("ck_users_trust_known"), "users", type_="check")
    for column in ("trust_set_by", "trust_set_at", "trust"):
        op.drop_column("users", column)
