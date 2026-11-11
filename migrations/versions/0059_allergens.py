"""Allergens on ingredients (allergens.py).

*SCOPING.md, Allergen data (Ray, 2026-11-06): yes, presented as
crowdsourced information.* The list is the US's nine major allergens and
the EU's fourteen together; an ingredient records, for any of them, that
it contains it, may contain it, or doesn't, the last overriding what a
broader ingredient records ("Vegan Butter" under "Butter"). Catalog data
under the ODbL, in the edit history and the dumps.

Revision ID: 0059
Revises: 0058
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALLERGENS = [
    ("milk", "Milk"),
    ("egg", "Egg"),
    ("fish", "Fish"),
    ("crustaceans", "Crustacean shellfish"),
    ("molluscs", "Molluscs"),
    ("tree_nuts", "Tree nuts"),
    ("peanuts", "Peanuts"),
    ("wheat", "Wheat"),
    ("gluten", "Gluten"),
    ("soy", "Soy"),
    ("sesame", "Sesame"),
    ("celery", "Celery"),
    ("mustard", "Mustard"),
    ("lupin", "Lupin"),
    ("sulphites", "Sulphites"),
]

# The revision trigger's parent for ingredient_aliases; an allergen hangs
# off its ingredient the same way, for the ingredient's History.
ALIAS_PARENT = "WHEN 'ingredient_aliases' THEN (row_ ->> 'ingredient_id')::uuid"
BOTH_PARENTS = (
    ALIAS_PARENT + "\n    WHEN 'ingredient_allergens' THEN (row_ ->> 'ingredient_id')::uuid"
)


def _swap_parent(old: str, new: str) -> None:
    op.execute(
        f"""
        DO $do$
        DECLARE
          body text := pg_get_functiondef('record_revision'::regproc);
          changed text := replace(body, $a${old}$a$, $b${new}$b$);
        BEGIN
          IF changed = body THEN
            RAISE EXCEPTION 'record_revision is not as migration 0040 wrote it';
          END IF;
          EXECUTE changed;
        END
        $do$;
        """
    )


def upgrade() -> None:
    allergens = op.create_table(
        "allergens",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("key ~ '^[a-z_]+$'", name=op.f("ck_allergens_key_format")),
        sa.CheckConstraint("label <> ''", name=op.f("ck_allergens_label_not_empty")),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_allergens")),
    )
    op.bulk_insert(
        allergens,
        [{"key": k, "label": label, "position": i} for i, (k, label) in enumerate(ALLERGENS)],
    )
    op.create_table(
        "ingredient_allergens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("ingredient_id", sa.UUID(), nullable=False),
        sa.Column("allergen", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('contains', 'may_contain', 'free')",
            name=op.f("ck_ingredient_allergens_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_ingredient_allergens_ingredient_id_ingredients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["allergen"],
            ["allergens.key"],
            name=op.f("fk_ingredient_allergens_allergen_allergens"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingredient_allergens")),
        sa.UniqueConstraint(
            "ingredient_id", "allergen", name=op.f("uq_ingredient_allergens_ingredient_id_allergen")
        ),
    )
    op.execute(
        "CREATE TRIGGER ingredient_allergens_updated_at BEFORE UPDATE ON ingredient_allergens "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER record_revision AFTER INSERT OR UPDATE OR DELETE ON ingredient_allergens"
        " FOR EACH ROW EXECUTE FUNCTION record_revision('none')"
    )
    _swap_parent(ALIAS_PARENT, BOTH_PARENTS)


def downgrade() -> None:
    _swap_parent(BOTH_PARENTS, ALIAS_PARENT)
    op.drop_table("ingredient_allergens")
    op.drop_table("allergens")
