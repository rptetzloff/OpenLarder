"""Sign-ups that followed a click on one of OpenLarder's ads (adclicks.py).

*Decided by Ray, 2026-11-13* (round 4, part E): Google Ads is told which ad
clicks led to a new account by a sheet it reads, with none of Google's
script on the site. This is the table the sheet is filled from: the click
id Google put on the ad's address, when it was clicked, when the account
was made, and when the row was exported.

No user column, on purpose, and no history trigger: nothing here names an
account, and the edit history is the catalog's.

Revision ID: 0075
Revises: 0074
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0075"
down_revision: str | None = "0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ad_conversions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("click_id", sa.Text(), nullable=False),
        sa.Column("click_id_type", sa.Text(), nullable=False),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "converted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('sign_up')", name=op.f("ck_ad_conversions_kind_known")),
        sa.CheckConstraint(
            "click_id_type IN ('gclid', 'gbraid', 'wbraid')",
            name=op.f("ck_ad_conversions_click_id_type_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ad_conversions")),
        sa.UniqueConstraint("kind", "click_id", name=op.f("uq_ad_conversions_kind_click_id")),
    )
    op.create_index(
        "ix_ad_conversions_pending",
        "ad_conversions",
        ["converted_at"],
        postgresql_where=sa.text("exported_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("ad_conversions")
