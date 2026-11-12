"""Alcohol recorded on ingredients, and diets that avoid two things only
together (Kosher: meat or poultry with milk).

*Ray, 2026-11-11: "yes to both".* Alcohol joins the list ingredients record
from, as meat did (0064), and Halal avoids it. A diet's row may now name a
second allergen: it avoids the first only in a recipe that also records
the second. Kosher gets meat with milk and poultry with milk; fish with
milk is left alone.

Revision ID: 0066
Revises: 0065
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0066"
down_revision: str | None = "0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TOGETHER = [("Kosher", "meat", "milk"), ("Kosher", "poultry", "milk")]


def upgrade() -> None:
    op.add_column("diet_allergens", sa.Column("with_allergen", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_diet_allergens_with_allergen_allergens"),
        "diet_allergens",
        "allergens",
        ["with_allergen"],
        ["key"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        op.f("ck_diet_allergens_with_another"), "diet_allergens", "with_allergen <> allergen"
    )
    op.execute(
        "INSERT INTO allergens (key, label, position)"
        " SELECT 'alcohol', 'Alcohol', coalesce(max(position), -1) + 1 FROM allergens"
    )
    # Seeds aren't edits.
    op.execute("ALTER TABLE diet_allergens DISABLE TRIGGER record_revision")
    op.execute(
        "INSERT INTO diet_allergens (diet_tag_id, allergen)"
        " SELECT t.id, 'alcohol' FROM tags t WHERE t.kind = 'diet' AND lower(t.name) = 'halal'"
        " AND NOT EXISTS (SELECT 1 FROM diet_allergens d"
        " WHERE d.diet_tag_id = t.id AND d.allergen = 'alcohol')"
    )
    for diet, key, other in TOGETHER:
        op.execute(
            sa.text(
                "INSERT INTO diet_allergens (diet_tag_id, allergen, with_allergen)"
                " SELECT t.id, :key, :other FROM tags t WHERE t.kind = 'diet'"
                " AND lower(t.name) = lower(:diet) AND NOT EXISTS (SELECT 1 FROM"
                " diet_allergens d WHERE d.diet_tag_id = t.id AND d.allergen = :key)"
            ).bindparams(diet=diet, key=key, other=other)
        )
    op.execute("ALTER TABLE diet_allergens ENABLE TRIGGER record_revision")


def downgrade() -> None:
    op.execute("DELETE FROM diet_allergens WHERE with_allergen IS NOT NULL")
    op.drop_constraint(op.f("ck_diet_allergens_with_another"), "diet_allergens", type_="check")
    op.drop_column("diet_allergens", "with_allergen")
    # Cascades to what ingredients and diets record of it.
    op.execute("DELETE FROM allergens WHERE key = 'alcohol'")
