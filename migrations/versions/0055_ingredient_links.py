"""Ingredients linked to USDA FoodData Central and Wikidata (fdc.py).

FoodData Central's generic foods are kept in fdc_foods, loaded from its bulk
download by an administrator (Admin, or `python -m openlarder.fdc load`);
an ingredient may name one of them, and a Wikidata item with its label.
Both are CC0, so the links go in the ODbL dumps too.

Revision ID: 0055
Revises: 0054
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fdc_foods",
        sa.Column("fdc_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("data_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("ndb_number", sa.Integer(), nullable=True),
        sa.Column("published", sa.Date(), nullable=True),
        sa.Column(
            "loaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("description <> ''", name=op.f("ck_fdc_foods_description_not_empty")),
        sa.CheckConstraint(
            "data_type IN ('foundation_food', 'sr_legacy_food', 'survey_fndds_food')",
            name=op.f("ck_fdc_foods_data_type_known"),
        ),
        sa.PrimaryKeyConstraint("fdc_id", name=op.f("pk_fdc_foods")),
    )
    op.create_index(op.f("ix_fdc_foods_ndb_number"), "fdc_foods", ["ndb_number"])
    op.create_index(
        "ix_fdc_foods_description_trgm",
        "fdc_foods",
        ["description"],
        postgresql_using="gin",
        postgresql_ops={"description": "gin_trgm_ops"},
    )
    op.add_column("ingredients", sa.Column("fdc_id", sa.Integer(), nullable=True))
    op.add_column("ingredients", sa.Column("wikidata_id", sa.Text(), nullable=True))
    op.add_column("ingredients", sa.Column("wikidata_label", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_ingredients_fdc_id_fdc_foods"),
        "ingredients",
        "fdc_foods",
        ["fdc_id"],
        ["fdc_id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_ingredients_fdc_id"), "ingredients", ["fdc_id"])
    op.create_index(op.f("ix_ingredients_wikidata_id"), "ingredients", ["wikidata_id"])
    op.create_check_constraint(
        op.f("ck_ingredients_wikidata_id_format"), "ingredients", "wikidata_id ~ '^Q[1-9][0-9]*$'"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_ingredients_wikidata_id_format"), "ingredients", type_="check")
    op.drop_index(op.f("ix_ingredients_wikidata_id"), "ingredients")
    op.drop_index(op.f("ix_ingredients_fdc_id"), "ingredients")
    op.drop_constraint(op.f("fk_ingredients_fdc_id_fdc_foods"), "ingredients", type_="foreignkey")
    op.drop_column("ingredients", "wikidata_label")
    op.drop_column("ingredients", "wikidata_id")
    op.drop_column("ingredients", "fdc_id")
    op.drop_table("fdc_foods")
