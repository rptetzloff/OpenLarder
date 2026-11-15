"""Producers: which ingredients each supplies, and the clicks on its link.

*Decided by Ray, 2026-11-13* (round 4, part D4): a producer is a farm, a
mill or a maker that sells ingredients itself. It's a row of shops, of the
kind "producer", which the table has allowed since 0073. This adds what a
producer has that a bookseller hasn't:

- producer_ingredients: the ingredients it supplies. A broad one covers
  what comes under it (producers.py). A change to it is in the edit
  history, as a change to the shop is (0074).
- producer_clicks: a click on its link, as the other click tables have it:
  which producer, the page it was on, when. Nothing about who.

No producer is added here: an administrator adds one from the site.

Revision ID: 0077
Revises: 0076
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0077"
down_revision: str | None = "0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "producer_ingredients",
        sa.Column("shop_id", sa.UUID(), nullable=False),
        sa.Column("ingredient_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            name=op.f("fk_producer_ingredients_shop_id_shops"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_producer_ingredients_ingredient_id_ingredients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("shop_id", "ingredient_id", name=op.f("pk_producer_ingredients")),
    )
    op.create_index(
        "ix_producer_ingredients_ingredient_id", "producer_ingredients", ["ingredient_id"]
    )
    op.execute(
        "CREATE TRIGGER record_revision AFTER INSERT OR UPDATE OR DELETE ON producer_ingredients"
        " FOR EACH ROW EXECUTE FUNCTION record_revision('none')"
    )
    op.create_table(
        "producer_clicks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("producer", sa.Text(), nullable=False),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("producer <> ''", name=op.f("ck_producer_clicks_producer_not_empty")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_producer_clicks")),
    )
    op.create_index("ix_producer_clicks_clicked_at", "producer_clicks", ["clicked_at"])


def downgrade() -> None:
    op.drop_table("producer_clicks")
    op.drop_table("producer_ingredients")
