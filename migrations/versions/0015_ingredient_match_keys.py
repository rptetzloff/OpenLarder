"""A matching key on canonical ingredients.

An ingredient line's option is matched to a canonical ingredient by a key
that ignores what doesn't change the ingredient: case, plurals, hyphens
and punctuation ("Cinnamon Sticks", "cinnamon stick"; "Long-Grain Rice",
"Long Grain Rice"). Accents are kept, so "Rosé" and "Rose" stay two
things. ingredients.match_key computes it; one ingredient per key.

Existing ingredients are keyed by the same function. Upgrade refuses if two
of them share a key, rather than choose which to keep: merge them first.

Revision ID: 0015
Revises: 0014
"""

from collections import Counter
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from openlarder.ingredients import match_key

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingredients", sa.Column("match_key", sa.Text()))
    bind = op.get_bind()
    keys = {i: match_key(n) for i, n in bind.execute(sa.text("SELECT id, name FROM ingredients"))}
    shared = [k for k, n in Counter(keys.values()).items() if n > 1]
    if shared:
        raise RuntimeError(f"Ingredients share a match key; merge them first: {shared[:5]}")
    for ingredient_id, key in keys.items():
        bind.execute(
            sa.text("UPDATE ingredients SET match_key = :k WHERE id = :i"),
            {"k": key, "i": ingredient_id},
        )
    op.alter_column("ingredients", "match_key", nullable=False)
    op.create_check_constraint(
        op.f("ck_ingredients_match_key_not_empty"), "ingredients", "match_key <> ''"
    )
    op.create_unique_constraint(op.f("uq_ingredients_match_key"), "ingredients", ["match_key"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_ingredients_match_key"), "ingredients", type_="unique")
    op.drop_constraint(op.f("ck_ingredients_match_key_not_empty"), "ingredients", type_="check")
    op.drop_column("ingredients", "match_key")
