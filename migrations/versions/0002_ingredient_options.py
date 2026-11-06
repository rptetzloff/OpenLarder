"""Ranked ingredient options: a line can name a first choice and fallbacks.

What a line points at moves from recipe_ingredients onto ingredient_options.
Each existing line becomes one rank-1 option carrying its old target, named
by the line's original text.

Downgrade refuses while any option holds something the old shape has no room
for -- a fallback, or a quantity of its own -- rather than drop it silently.
A lone option's name is not carried back; the line's original text holds it.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_recipe_ingredients_recipe_id_id", "recipe_ingredients", ["recipe_id", "id"]
    )

    op.create_table(
        "ingredient_options",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("recipe_ingredient_id", UUID, nullable=False),
        sa.Column("recipe_id", UUID, nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Text()),
        sa.Column("unit", sa.Text()),
        sa.Column("ingredient_id", UUID),
        sa.Column("sub_recipe_id", UUID),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingredient_options"),
        sa.ForeignKeyConstraint(
            ["recipe_id", "recipe_ingredient_id"],
            ["recipe_ingredients.recipe_id", "recipe_ingredients.id"],
            ondelete="CASCADE",
            name="fk_ingredient_options_line",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            ondelete="RESTRICT",
            name="fk_ingredient_options_ingredient_id_ingredients",
        ),
        sa.ForeignKeyConstraint(
            ["sub_recipe_id"],
            ["recipes.id"],
            ondelete="RESTRICT",
            name="fk_ingredient_options_sub_recipe_id_recipes",
        ),
        sa.UniqueConstraint(
            "recipe_ingredient_id", "rank", name="uq_ingredient_options_recipe_ingredient_id_rank"
        ),
        sa.CheckConstraint("rank >= 1", name="ck_ingredient_options_rank_positive"),
        sa.CheckConstraint("name <> ''", name="ck_ingredient_options_name_not_empty"),
        sa.CheckConstraint(
            "num_nonnulls(ingredient_id, sub_recipe_id) <= 1",
            name="ck_ingredient_options_one_target_at_most",
        ),
        sa.CheckConstraint(
            "sub_recipe_id <> recipe_id", name="ck_ingredient_options_not_own_sub_recipe"
        ),
    )
    op.create_index("ix_ingredient_options_ingredient_id", "ingredient_options", ["ingredient_id"])
    op.create_index("ix_ingredient_options_sub_recipe_id", "ingredient_options", ["sub_recipe_id"])
    op.execute(
        "CREATE TRIGGER ingredient_options_updated_at BEFORE UPDATE ON ingredient_options "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.execute(
        """
        INSERT INTO ingredient_options
            (recipe_ingredient_id, recipe_id, rank, name, ingredient_id, sub_recipe_id)
        SELECT id, recipe_id, 1, original_text, ingredient_id, sub_recipe_id
        FROM recipe_ingredients
        """
    )

    # Their indexes, foreign keys and CHECKs go with them.
    op.drop_column("recipe_ingredients", "ingredient_id")
    op.drop_column("recipe_ingredients", "sub_recipe_id")


def downgrade() -> None:
    kept = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM ingredient_options"
                " WHERE rank > 1 OR quantity IS NOT NULL OR unit IS NOT NULL"
            )
        )
        .scalar_one()
    )
    if kept:
        raise RuntimeError(
            f"{kept} ingredient option(s) hold a fallback or their own quantity, which the"
            " previous schema cannot store. Remove them first if losing them is intended."
        )

    op.add_column("recipe_ingredients", sa.Column("ingredient_id", UUID))
    op.add_column("recipe_ingredients", sa.Column("sub_recipe_id", UUID))
    op.execute(
        """
        UPDATE recipe_ingredients ri
        SET ingredient_id = o.ingredient_id, sub_recipe_id = o.sub_recipe_id
        FROM ingredient_options o
        WHERE o.recipe_ingredient_id = ri.id AND o.rank = 1
        """
    )
    op.create_foreign_key(
        "fk_recipe_ingredients_ingredient_id_ingredients",
        "recipe_ingredients",
        "ingredients",
        ["ingredient_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_recipe_ingredients_sub_recipe_id_recipes",
        "recipe_ingredients",
        "recipes",
        ["sub_recipe_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_recipe_ingredients_one_target_at_most",
        "recipe_ingredients",
        "num_nonnulls(ingredient_id, sub_recipe_id) <= 1",
    )
    op.create_check_constraint(
        "ck_recipe_ingredients_not_own_sub_recipe",
        "recipe_ingredients",
        "sub_recipe_id <> recipe_id",
    )
    op.create_index("ix_recipe_ingredients_ingredient_id", "recipe_ingredients", ["ingredient_id"])
    op.create_index("ix_recipe_ingredients_sub_recipe_id", "recipe_ingredients", ["sub_recipe_id"])

    op.drop_table("ingredient_options")
    op.drop_constraint("uq_recipe_ingredients_recipe_id_id", "recipe_ingredients", type_="unique")
