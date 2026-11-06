"""The catalog: works, editions, recipes, pages, ingredients, and tags.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
TAG_KIND = pg.ENUM("course", "cuisine", "diet", "technique", name="tag_kind", create_type=False)

# Tables with an updated_at column, maintained by the set_updated_at trigger.
TIMESTAMPED = (
    "works",
    "editions",
    "purchase_links",
    "recipes",
    "recipe_pages",
    "ingredients",
    "ingredient_aliases",
    "recipe_ingredients",
    "tags",
)


def _id() -> sa.Column:
    return sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _trgm(table: str, column: str) -> None:
    op.create_index(
        f"ix_{table}_{column}_trgm",
        table,
        [column],
        postgresql_using="gin",
        postgresql_ops={column: "gin_trgm_ops"},
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    TAG_KIND.create(op.get_bind())

    op.create_table(
        "works",
        _id(),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text()),
        sa.Column("authors", pg.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("open_library_work_id", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_works"),
        sa.UniqueConstraint("open_library_work_id", name="uq_works_open_library_work_id"),
        sa.CheckConstraint("title <> ''", name="ck_works_title_not_empty"),
    )
    _trgm("works", "title")

    op.create_table(
        "editions",
        _id(),
        sa.Column("work_id", UUID, nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("isbn13", sa.Text()),
        sa.Column("publisher", sa.Text()),
        sa.Column("published_year", sa.SmallInteger()),
        sa.Column("open_library_edition_id", sa.Text()),
        sa.Column("cover_key", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_editions"),
        sa.ForeignKeyConstraint(
            ["work_id"], ["works.id"], ondelete="CASCADE", name="fk_editions_work_id_works"
        ),
        sa.UniqueConstraint("work_id", "id", name="uq_editions_work_id_id"),
        sa.UniqueConstraint("isbn13", name="uq_editions_isbn13"),
        sa.UniqueConstraint("open_library_edition_id", name="uq_editions_open_library_edition_id"),
        sa.CheckConstraint("isbn13 ~ '^97[89][0-9]{10}$'", name="ck_editions_isbn13_format"),
        sa.CheckConstraint(
            "published_year BETWEEN 1400 AND 2200", name="ck_editions_published_year_range"
        ),
    )

    op.create_table(
        "purchase_links",
        _id(),
        sa.Column("edition_id", UUID, nullable=False),
        sa.Column("retailer", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_links"),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            ["editions.id"],
            ondelete="CASCADE",
            name="fk_purchase_links_edition_id_editions",
        ),
        sa.UniqueConstraint("edition_id", "retailer", name="uq_purchase_links_edition_id_retailer"),
        sa.CheckConstraint("retailer <> ''", name="ck_purchase_links_retailer_not_empty"),
    )

    op.create_table(
        "recipes",
        _id(),
        sa.Column("work_id", UUID, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("online_url", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_recipes"),
        sa.ForeignKeyConstraint(
            ["work_id"], ["works.id"], ondelete="CASCADE", name="fk_recipes_work_id_works"
        ),
        sa.UniqueConstraint("work_id", "id", name="uq_recipes_work_id_id"),
        sa.CheckConstraint("title <> ''", name="ck_recipes_title_not_empty"),
    )
    op.create_index("ix_recipes_work_id_title", "recipes", ["work_id", "title"])
    _trgm("recipes", "title")

    op.create_table(
        "recipe_pages",
        sa.Column("recipe_id", UUID, nullable=False),
        sa.Column("edition_id", UUID, nullable=False),
        sa.Column("work_id", UUID, nullable=False),
        sa.Column("page", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("recipe_id", "edition_id", name="pk_recipe_pages"),
        sa.ForeignKeyConstraint(
            ["work_id", "recipe_id"],
            ["recipes.work_id", "recipes.id"],
            ondelete="CASCADE",
            name="fk_recipe_pages_work_id_recipe_id_recipes",
        ),
        sa.ForeignKeyConstraint(
            ["work_id", "edition_id"],
            ["editions.work_id", "editions.id"],
            ondelete="CASCADE",
            name="fk_recipe_pages_work_id_edition_id_editions",
        ),
        sa.CheckConstraint("page <> ''", name="ck_recipe_pages_page_not_empty"),
    )
    op.create_index("ix_recipe_pages_edition_id", "recipe_pages", ["edition_id"])

    op.create_table(
        "ingredients",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("shopping_term", sa.Text()),
        sa.Column("parent_id", UUID),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_ingredients"),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["ingredients.id"],
            ondelete="RESTRICT",
            name="fk_ingredients_parent_id_ingredients",
        ),
        sa.CheckConstraint("name <> ''", name="ck_ingredients_name_not_empty"),
        sa.CheckConstraint("parent_id <> id", name="ck_ingredients_not_own_parent"),
    )
    op.create_index("uq_ingredients_name", "ingredients", [sa.text("lower(name)")], unique=True)
    op.create_index("ix_ingredients_parent_id", "ingredients", ["parent_id"])
    _trgm("ingredients", "name")

    op.create_table(
        "ingredient_aliases",
        _id(),
        sa.Column("ingredient_id", UUID, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("region", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_ingredient_aliases"),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            ondelete="CASCADE",
            name="fk_ingredient_aliases_ingredient_id_ingredients",
        ),
        sa.CheckConstraint("name <> ''", name="ck_ingredient_aliases_name_not_empty"),
        sa.CheckConstraint(
            "region IN ('US', 'UK', 'AU')", name="ck_ingredient_aliases_region_known"
        ),
    )
    op.create_index(
        "uq_ingredient_aliases_name_region",
        "ingredient_aliases",
        [sa.text("lower(name)"), "region"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index("ix_ingredient_aliases_ingredient_id", "ingredient_aliases", ["ingredient_id"])
    _trgm("ingredient_aliases", "name")

    op.create_table(
        "recipe_ingredients",
        _id(),
        sa.Column("recipe_id", UUID, nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Text()),
        sa.Column("unit", sa.Text()),
        sa.Column("form", sa.Text()),
        sa.Column("prep", sa.Text()),
        sa.Column("ingredient_id", UUID),
        sa.Column("sub_recipe_id", UUID),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_recipe_ingredients"),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            ondelete="CASCADE",
            name="fk_recipe_ingredients_recipe_id_recipes",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            ondelete="RESTRICT",
            name="fk_recipe_ingredients_ingredient_id_ingredients",
        ),
        sa.ForeignKeyConstraint(
            ["sub_recipe_id"],
            ["recipes.id"],
            ondelete="RESTRICT",
            name="fk_recipe_ingredients_sub_recipe_id_recipes",
        ),
        sa.UniqueConstraint(
            "recipe_id", "position", name="uq_recipe_ingredients_recipe_id_position"
        ),
        sa.CheckConstraint(
            "original_text <> ''", name="ck_recipe_ingredients_original_text_not_empty"
        ),
        sa.CheckConstraint(
            "num_nonnulls(ingredient_id, sub_recipe_id) <= 1",
            name="ck_recipe_ingredients_one_target_at_most",
        ),
        sa.CheckConstraint(
            "sub_recipe_id <> recipe_id", name="ck_recipe_ingredients_not_own_sub_recipe"
        ),
    )
    op.create_index("ix_recipe_ingredients_ingredient_id", "recipe_ingredients", ["ingredient_id"])
    op.create_index("ix_recipe_ingredients_sub_recipe_id", "recipe_ingredients", ["sub_recipe_id"])

    op.create_table(
        "tags",
        _id(),
        sa.Column("kind", TAG_KIND, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_tags"),
        sa.CheckConstraint("name <> ''", name="ck_tags_name_not_empty"),
    )
    op.create_index("uq_tags_kind_name", "tags", ["kind", sa.text("lower(name)")], unique=True)

    op.create_table(
        "work_tags",
        sa.Column("work_id", UUID, nullable=False),
        sa.Column("tag_id", UUID, nullable=False),
        sa.PrimaryKeyConstraint("work_id", "tag_id", name="pk_work_tags"),
        sa.ForeignKeyConstraint(
            ["work_id"], ["works.id"], ondelete="CASCADE", name="fk_work_tags_work_id_works"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], ondelete="CASCADE", name="fk_work_tags_tag_id_tags"
        ),
    )
    op.create_index("ix_work_tags_tag_id", "work_tags", ["tag_id"])

    op.create_table(
        "recipe_tags",
        sa.Column("recipe_id", UUID, nullable=False),
        sa.Column("tag_id", UUID, nullable=False),
        sa.PrimaryKeyConstraint("recipe_id", "tag_id", name="pk_recipe_tags"),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            ondelete="CASCADE",
            name="fk_recipe_tags_recipe_id_recipes",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], ondelete="CASCADE", name="fk_recipe_tags_tag_id_tags"
        ),
    )
    op.create_index("ix_recipe_tags_tag_id", "recipe_tags", ["tag_id"])

    op.execute(
        """
        CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END
        $$
        """
    )
    for table in TIMESTAMPED:
        op.execute(
            f"CREATE TRIGGER {table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )

    # A recipe's tags: its own plus its book's. Computed on read, so tagging
    # a book never has to be copied onto every recipe in it. A tag set on
    # both appears once, as the recipe's own.
    op.execute(
        """
        CREATE VIEW recipe_effective_tags AS
        SELECT rt.recipe_id, rt.tag_id, false AS inherited
        FROM recipe_tags rt
        UNION ALL
        SELECT r.id, wt.tag_id, true
        FROM recipes r
        JOIN work_tags wt ON wt.work_id = r.work_id
        WHERE NOT EXISTS (
            SELECT 1 FROM recipe_tags rt WHERE rt.recipe_id = r.id AND rt.tag_id = wt.tag_id
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW recipe_effective_tags")
    for table in (
        "recipe_tags",
        "work_tags",
        "tags",
        "recipe_ingredients",
        "ingredient_aliases",
        "ingredients",
        "recipe_pages",
        "recipes",
        "purchase_links",
        "editions",
        "works",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION set_updated_at()")
    TAG_KIND.drop(op.get_bind())
    # pg_trgm stays: another schema in the same database may use it.
