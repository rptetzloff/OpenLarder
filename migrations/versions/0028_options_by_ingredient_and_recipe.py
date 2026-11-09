"""Index ingredient options by ingredient, then recipe.

Counting the recipes that use each ingredient (the Ingredients list, and the
search box's suggestions at every keystroke) sorted every option on disk
once private collections were filtered out (#64): 117 ms on a catalog the
size of production's, against 25 ms with this index read in order. It
replaces the index on ingredient_id alone, which it begins with.

Revision ID: 0028
Revises: 0027
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_ingredient_options_ingredient_id_recipe_id"),
        "ingredient_options",
        ["ingredient_id", "recipe_id"],
    )
    op.drop_index(op.f("ix_ingredient_options_ingredient_id"), "ingredient_options")


def downgrade() -> None:
    op.create_index(
        op.f("ix_ingredient_options_ingredient_id"), "ingredient_options", ["ingredient_id"]
    )
    op.drop_index(op.f("ix_ingredient_options_ingredient_id_recipe_id"), "ingredient_options")
