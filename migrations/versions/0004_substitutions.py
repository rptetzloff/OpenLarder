"""Substitutions: one ingredient or recipe standing in for another, usually for a diet.

Downgrade refuses while any substitution exists, rather than drop them.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
TAG_KIND = pg.ENUM("course", "cuisine", "diet", "technique", name="tag_kind", create_type=False)


def upgrade() -> None:
    op.create_unique_constraint("uq_tags_kind_id", "tags", ["kind", "id"])

    op.create_table(
        "substitutions",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("from_ingredient_id", UUID),
        sa.Column("from_recipe_id", UUID),
        sa.Column("to_ingredient_id", UUID),
        sa.Column("to_recipe_id", UUID),
        sa.Column("diet_tag_id", UUID),
        sa.Column("diet_kind", TAG_KIND, server_default="diet", nullable=False),
        sa.Column("source_edition_id", UUID),
        sa.Column("source_page", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_substitutions"),
        sa.ForeignKeyConstraint(
            ["from_ingredient_id"],
            ["ingredients.id"],
            ondelete="RESTRICT",
            name="fk_substitutions_from_ingredient_id_ingredients",
        ),
        sa.ForeignKeyConstraint(
            ["from_recipe_id"],
            ["recipes.id"],
            ondelete="CASCADE",
            name="fk_substitutions_from_recipe_id_recipes",
        ),
        sa.ForeignKeyConstraint(
            ["to_ingredient_id"],
            ["ingredients.id"],
            ondelete="RESTRICT",
            name="fk_substitutions_to_ingredient_id_ingredients",
        ),
        sa.ForeignKeyConstraint(
            ["to_recipe_id"],
            ["recipes.id"],
            ondelete="CASCADE",
            name="fk_substitutions_to_recipe_id_recipes",
        ),
        sa.ForeignKeyConstraint(
            ["diet_kind", "diet_tag_id"],
            ["tags.kind", "tags.id"],
            ondelete="RESTRICT",
            name="fk_substitutions_diet_tag",
        ),
        sa.ForeignKeyConstraint(
            ["source_edition_id"],
            ["editions.id"],
            ondelete="RESTRICT",
            name="fk_substitutions_source_edition_id_editions",
        ),
        sa.CheckConstraint(
            "num_nonnulls(from_ingredient_id, from_recipe_id) = 1",
            name="ck_substitutions_one_from",
        ),
        sa.CheckConstraint(
            "num_nonnulls(to_ingredient_id, to_recipe_id) = 1", name="ck_substitutions_one_to"
        ),
        sa.CheckConstraint(
            "from_ingredient_id <> to_ingredient_id AND from_recipe_id <> to_recipe_id",
            name="ck_substitutions_not_itself",
        ),
        sa.CheckConstraint(
            "source_page IS NULL OR source_edition_id IS NOT NULL",
            name="ck_substitutions_page_needs_edition",
        ),
        sa.CheckConstraint("source_page <> ''", name="ck_substitutions_source_page_not_empty"),
        sa.CheckConstraint("diet_kind = 'diet'", name="ck_substitutions_diet_kind_is_diet"),
    )
    op.create_index(
        "uq_substitutions_swap",
        "substitutions",
        [
            "from_ingredient_id",
            "from_recipe_id",
            "to_ingredient_id",
            "to_recipe_id",
            "diet_tag_id",
            "source_edition_id",
        ],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    for column in ("to_ingredient_id", "from_recipe_id", "to_recipe_id", "diet_tag_id"):
        op.create_index(f"ix_substitutions_{column}", "substitutions", [column])
    op.execute(
        "CREATE TRIGGER substitutions_updated_at BEFORE UPDATE ON substitutions "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    kept = op.get_bind().execute(sa.text("SELECT count(*) FROM substitutions")).scalar_one()
    if kept:
        raise RuntimeError(
            f"{kept} substitution(s) exist, and the previous schema has nowhere to keep them."
            " Remove them first if losing them is intended."
        )
    op.drop_table("substitutions")
    op.drop_constraint("uq_tags_kind_id", "tags", type_="unique")
