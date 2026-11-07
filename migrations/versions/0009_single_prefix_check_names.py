"""Gives every CHECK constraint the single-prefix name the models describe.

The naming convention for CHECK constraints is ck_<table>_<name>, and it is
applied to whatever name is given. Migrations 0001 to 0008 gave full names
such as "ck_users_issuer_not_empty", so the database has
"ck_users_ck_users_issuer_not_empty", and one name too long for Postgres'
63 characters was cut short with a hash. The models give bare names, so
they already describe the intended ones; alembic check cannot see CHECK
constraints, which is how the two drifted. tests/test_constraint_names.py
now compares them. From here on, a migration names a CHECK constraint with
op.f("ck_<table>_<name>"), which marks it as final.

Downgrade restores the old names, because the earlier migrations' downgrades
drop constraints by them.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, name as created, name the models give)
RENAMES = [
    (
        "author_links",
        "ck_author_links_ck_author_links_url_not_empty",
        "ck_author_links_url_not_empty",
    ),
    ("authors", "ck_authors_ck_authors_kind_known", "ck_authors_kind_known"),
    ("authors", "ck_authors_ck_authors_name_not_empty", "ck_authors_name_not_empty"),
    ("authors", "ck_authors_ck_authors_wikidata_id_format", "ck_authors_wikidata_id_format"),
    ("editions", "ck_editions_ck_editions_isbn13_format", "ck_editions_isbn13_format"),
    (
        "editions",
        "ck_editions_ck_editions_published_year_range",
        "ck_editions_published_year_range",
    ),
    (
        "ingredient_aliases",
        "ck_ingredient_aliases_ck_ingredient_aliases_name_not_empty",
        "ck_ingredient_aliases_name_not_empty",
    ),
    (
        "ingredient_aliases",
        "ck_ingredient_aliases_ck_ingredient_aliases_region_known",
        "ck_ingredient_aliases_region_known",
    ),
    (
        "ingredient_options",
        "ck_ingredient_options_ck_ingredient_options_name_not_empty",
        "ck_ingredient_options_name_not_empty",
    ),
    (
        "ingredient_options",
        "ck_ingredient_options_ck_ingredient_options_not_own_sub_recipe",
        "ck_ingredient_options_not_own_sub_recipe",
    ),
    (
        "ingredient_options",
        "ck_ingredient_options_ck_ingredient_options_one_target_at_most",
        "ck_ingredient_options_one_target_at_most",
    ),
    (
        "ingredient_options",
        "ck_ingredient_options_ck_ingredient_options_rank_positive",
        "ck_ingredient_options_rank_positive",
    ),
    (
        "ingredients",
        "ck_ingredients_ck_ingredients_name_not_empty",
        "ck_ingredients_name_not_empty",
    ),
    (
        "ingredients",
        "ck_ingredients_ck_ingredients_not_own_parent",
        "ck_ingredients_not_own_parent",
    ),
    (
        "purchase_links",
        "ck_purchase_links_ck_purchase_links_retailer_not_empty",
        "ck_purchase_links_retailer_not_empty",
    ),
    (
        "recipe_ingredients",
        "ck_recipe_ingredients_ck_recipe_ingredients_original_te_c22e",
        "ck_recipe_ingredients_original_text_not_empty",
    ),
    (
        "recipe_pages",
        "ck_recipe_pages_ck_recipe_pages_page_not_empty",
        "ck_recipe_pages_page_not_empty",
    ),
    ("recipes", "ck_recipes_ck_recipes_title_not_empty", "ck_recipes_title_not_empty"),
    (
        "substitutions",
        "ck_substitutions_ck_substitutions_diet_kind_is_diet",
        "ck_substitutions_diet_kind_is_diet",
    ),
    (
        "substitutions",
        "ck_substitutions_ck_substitutions_not_itself",
        "ck_substitutions_not_itself",
    ),
    (
        "substitutions",
        "ck_substitutions_ck_substitutions_note_not_empty",
        "ck_substitutions_note_not_empty",
    ),
    ("substitutions", "ck_substitutions_ck_substitutions_one_from", "ck_substitutions_one_from"),
    ("substitutions", "ck_substitutions_ck_substitutions_one_to", "ck_substitutions_one_to"),
    (
        "substitutions",
        "ck_substitutions_ck_substitutions_page_needs_edition",
        "ck_substitutions_page_needs_edition",
    ),
    (
        "substitutions",
        "ck_substitutions_ck_substitutions_source_page_not_empty",
        "ck_substitutions_source_page_not_empty",
    ),
    ("tags", "ck_tags_ck_tags_name_not_empty", "ck_tags_name_not_empty"),
    ("users", "ck_users_ck_users_display_name_shape", "ck_users_display_name_shape"),
    ("users", "ck_users_ck_users_issuer_not_empty", "ck_users_issuer_not_empty"),
    ("users", "ck_users_ck_users_subject_not_empty", "ck_users_subject_not_empty"),
    ("users", "ck_users_ck_users_suggested_name_not_empty", "ck_users_suggested_name_not_empty"),
    (
        "user_sessions",
        "ck_user_sessions_ck_user_sessions_expires_after_created",
        "ck_user_sessions_expires_after_created",
    ),
    (
        "user_sessions",
        "ck_user_sessions_ck_user_sessions_id_token_not_empty",
        "ck_user_sessions_id_token_not_empty",
    ),
    (
        "user_sessions",
        "ck_user_sessions_ck_user_sessions_token_hash_is_sha256",
        "ck_user_sessions_token_hash_is_sha256",
    ),
    (
        "work_credits",
        "ck_work_credits_ck_work_credits_credited_as_not_empty",
        "ck_work_credits_credited_as_not_empty",
    ),
    ("work_credits", "ck_work_credits_ck_work_credits_role_known", "ck_work_credits_role_known"),
    ("works", "ck_works_ck_works_title_not_empty", "ck_works_title_not_empty"),
]


def upgrade() -> None:
    for table, old, new in RENAMES:
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"')


def downgrade() -> None:
    for table, old, new in RENAMES:
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{new}" TO "{old}"')
