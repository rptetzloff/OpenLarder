"""Meat, poultry and pork, recorded on ingredients as allergens are.

*Ray, 2026-11-11:* so Vegan, Vegetarian and Pescetarian check for more than
milk, egg and seafood, and because poultry is an allergy in his family.
Each is recorded, inherited, suggested and listed on a recipe exactly as an
allergen is. Meat here is red meat and game; pork is its own, for diets
that avoid it alone (halal, kosher), and so is poultry.

Vegan, Vegetarian and Pescetarian avoid all three.

Revision ID: 0064
Revises: 0063
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064"
down_revision: str | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW = [
    ("meat", "Meat (beef, lamb, game)"),
    ("poultry", "Poultry"),
    ("pork", "Pork"),
]
DIETS = ["Vegan", "Vegetarian", "Pescetarian"]


def upgrade() -> None:
    # Seeds aren't edits: 0061's went in before the table had its trigger.
    op.execute("ALTER TABLE diet_allergens DISABLE TRIGGER record_revision")
    for key, label in NEW:
        op.execute(
            sa.text(
                "INSERT INTO allergens (key, label, position)"
                " SELECT :key, :label, coalesce(max(position), -1) + 1 FROM allergens"
            ).bindparams(key=key, label=label)
        )
        for diet in DIETS:
            op.execute(
                sa.text(
                    "INSERT INTO diet_allergens (diet_tag_id, allergen)"
                    " SELECT id, :key FROM tags WHERE kind = 'diet' AND lower(name) = lower(:diet)"
                ).bindparams(key=key, diet=diet)
            )
    op.execute("ALTER TABLE diet_allergens ENABLE TRIGGER record_revision")


def downgrade() -> None:
    # Cascades to what ingredients and diets record of them.
    op.execute("DELETE FROM allergens WHERE key IN ('meat', 'poultry', 'pork')")
