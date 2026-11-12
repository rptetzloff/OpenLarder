"""Which allergens each diet avoids, so a recipe's page can show, for a
diet, the lines whose ingredients record them and the swaps recorded for
those (diets.py).

*SCOPING.md, Allergen data: "This lets the site offer substitutions for a
diet automatically, not only where someone has entered one."* Vegan and
Vegetarian avoid more than allergens; the page says which allergens it
checks. Paleo, AIP and Low-FODMAP aren't allergen diets and avoid none
until a moderator says otherwise. Catalog data, in the history and dumps.

*Ray, 2026-11-11:* Gluten-Free avoids every gluten grain, so the gluten
allergen says so in its label: the EU's "cereals containing gluten",
wheat, barley, rye and their kin. And Pescetarian is a diet, for tagging
and swaps; it avoids meat, which isn't an allergen, so it checks nothing.

Revision ID: 0061
Revises: 0060
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEAFOOD = ["fish", "crustaceans", "molluscs"]
AVOIDS = {
    "Dairy-Free": ["milk"],
    "Gluten-Free": ["gluten", "wheat"],
    "Egg-Free": ["egg"],
    "Nut-Free": ["tree_nuts", "peanuts"],
    "Soy-Free": ["soy"],
    "Vegan": ["milk", "egg", *SEAFOOD],
    "Vegetarian": SEAFOOD,
}


def upgrade() -> None:
    op.create_table(
        "diet_allergens",
        sa.Column("diet_tag_id", sa.UUID(), nullable=False),
        sa.Column("allergen", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["diet_tag_id"],
            ["tags.id"],
            name=op.f("fk_diet_allergens_diet_tag_id_tags"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["allergen"],
            ["allergens.key"],
            name=op.f("fk_diet_allergens_allergen_allergens"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("diet_tag_id", "allergen", name=op.f("pk_diet_allergens")),
    )
    op.create_index(op.f("ix_diet_allergens_allergen"), "diet_allergens", ["allergen"])
    for diet, keys in AVOIDS.items():
        for key in keys:
            op.execute(
                sa.text(
                    "INSERT INTO diet_allergens (diet_tag_id, allergen)"
                    " SELECT id, :key FROM tags WHERE kind = 'diet' AND lower(name) = lower(:diet)"
                ).bindparams(key=key, diet=diet)
            )
    op.execute("UPDATE allergens SET label = 'Gluten (wheat, barley, rye)' WHERE key = 'gluten'")
    # A seed, not an edit: kept out of the history (as 0065's are).
    op.execute("ALTER TABLE tags DISABLE TRIGGER record_revision")
    op.execute(
        "INSERT INTO tags (kind, name) SELECT 'diet', 'Pescetarian'"
        " WHERE NOT EXISTS (SELECT 1 FROM tags WHERE kind = 'diet'"
        " AND lower(name) = 'pescetarian')"
    )
    op.execute("ALTER TABLE tags ENABLE TRIGGER record_revision")
    op.execute(
        "CREATE TRIGGER record_revision AFTER INSERT OR UPDATE OR DELETE ON diet_allergens"
        " FOR EACH ROW EXECUTE FUNCTION record_revision('none')"
    )


def downgrade() -> None:
    op.execute("UPDATE allergens SET label = 'Gluten' WHERE key = 'gluten'")
    op.drop_table("diet_allergens")
