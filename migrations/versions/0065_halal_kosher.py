"""Halal and Kosher as diets, for tagging and for a recipe's diet check.

*Ray, 2026-11-11: "many cookbooks have it".* Each checks only the part of
the diet the catalog records: Halal avoids pork; Kosher avoids pork,
crustaceans and molluscs. How the meat was slaughtered, alcohol, fish
without scales and meat with milk aren't recorded, and the check says
which it looks for and nothing else. Moderators change what each avoids
on Admin.

Revision ID: 0065
Revises: 0064
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0065"
down_revision: str | None = "0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AVOIDS = {
    "Halal": ["pork"],
    "Kosher": ["pork", "crustaceans", "molluscs"],
}
SEEDED = ("tags", "diet_allergens")


def upgrade() -> None:
    # Seeds aren't edits.
    for table in SEEDED:
        op.execute(f"ALTER TABLE {table} DISABLE TRIGGER record_revision")
    for diet, keys in AVOIDS.items():
        op.execute(
            sa.text(
                "INSERT INTO tags (kind, name) SELECT 'diet', :diet"
                " WHERE NOT EXISTS (SELECT 1 FROM tags WHERE kind = 'diet'"
                " AND lower(name) = lower(:diet))"
            ).bindparams(diet=diet)
        )
        for key in keys:
            op.execute(
                sa.text(
                    "INSERT INTO diet_allergens (diet_tag_id, allergen)"
                    " SELECT t.id, :key FROM tags t WHERE t.kind = 'diet'"
                    " AND lower(t.name) = lower(:diet) AND NOT EXISTS (SELECT 1 FROM"
                    " diet_allergens d WHERE d.diet_tag_id = t.id AND d.allergen = :key)"
                ).bindparams(key=key, diet=diet)
            )
    for table in SEEDED:
        op.execute(f"ALTER TABLE {table} ENABLE TRIGGER record_revision")


def downgrade() -> None:
    # The tags stay: recipes may be tagged with them by now.
    op.execute(
        "DELETE FROM diet_allergens WHERE diet_tag_id IN"
        " (SELECT id FROM tags WHERE kind = 'diet' AND lower(name) IN ('halal', 'kosher'))"
    )
