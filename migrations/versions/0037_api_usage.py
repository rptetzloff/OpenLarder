"""API use by programs outside the site, a day at a time, for admins.

A caller with a key is the key; one without is a pseudonym (a keyed hash of
its address) and its network, never the address. Kept 30 days (usage.py).
*Ray, 2026-11-09.*

Revision ID: 0037
Revises: 0036
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_usage",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("caller", sa.Text(), nullable=False),
        sa.Column("key_id", sa.UUID(), nullable=True),
        sa.Column("network", sa.Text(), nullable=True),
        sa.Column("requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("searches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("refused", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("caller <> ''", name=op.f("ck_api_usage_caller_not_empty")),
        sa.CheckConstraint(
            "requests >= 0 AND searches >= 0 AND refused >= 0",
            name=op.f("ck_api_usage_counts_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["key_id"],
            ["api_keys.id"],
            name=op.f("fk_api_usage_key_id_api_keys"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("day", "caller", name=op.f("pk_api_usage")),
    )
    op.create_index(op.f("ix_api_usage_key_id"), "api_usage", ["key_id"])


def downgrade() -> None:
    op.drop_table("api_usage")
