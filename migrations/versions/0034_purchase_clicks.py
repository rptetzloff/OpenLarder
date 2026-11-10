"""Clicks on buy links: which edition, which shop, when, and from which page.

Buy links go through /go/, which records the click and sends it on with the
affiliate ID (SCOPING.md, Tracking and disclosure). The shops report sales,
not which OpenLarder page sent them; this does. Nothing about who clicked:
no user, IP address or cookie.

Revision ID: 0034
Revises: 0033
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchase_clicks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("edition_id", sa.UUID(), nullable=False),
        sa.Column("retailer", sa.Text(), nullable=False),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("retailer <> ''", name=op.f("ck_purchase_clicks_retailer_not_empty")),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            ["editions.id"],
            name=op.f("fk_purchase_clicks_edition_id_editions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_clicks")),
    )
    op.create_index("ix_purchase_clicks_clicked_at", "purchase_clicks", ["clicked_at"])
    op.create_index("ix_purchase_clicks_edition_id", "purchase_clicks", ["edition_id"])


def downgrade() -> None:
    op.drop_table("purchase_clicks")
