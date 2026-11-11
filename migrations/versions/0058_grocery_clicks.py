"""Clicks on ingredients' grocery links (grocery.py): which ingredient,
which grocer, when, and from which page; nothing about who clicked.

Revision ID: 0058
Revises: 0057
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grocery_clicks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("ingredient_id", sa.UUID(), nullable=False),
        sa.Column("grocer", sa.Text(), nullable=False),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("grocer <> ''", name=op.f("ck_grocery_clicks_grocer_not_empty")),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_grocery_clicks_ingredient_id_ingredients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grocery_clicks")),
    )
    op.create_index("ix_grocery_clicks_clicked_at", "grocery_clicks", ["clicked_at"])
    op.create_index("ix_grocery_clicks_ingredient_id", "grocery_clicks", ["ingredient_id"])


def downgrade() -> None:
    op.drop_table("grocery_clicks")
