"""Who added a recipe, and flags on recipes that need a person to look.

A flag says something about a recipe looked wrong when it was entered or
imported: a repeated title, no ingredients, a line that was removed. Until
review exists, admins see every open flag and each person sees the flags on
recipes they added. Dealing with a flag records how (fixed, or dismissed as
wrong) and who, so review can take the history over. *Ray, 2026-11-07.*

created_by is set null if the user is deleted: the recipe is catalog data
and outlives the account that added it.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
KINDS = "'duplicate_title', 'no_ingredients', 'no_page', 'line_removed', 'line_fragment'"


def upgrade() -> None:
    op.add_column("recipes", sa.Column("created_by", UUID))
    op.create_foreign_key(
        "fk_recipes_created_by_users",
        "recipes",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_recipes_created_by", "recipes", ["created_by"])

    op.create_table(
        "recipe_flags",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("recipe_id", UUID, nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", UUID),
        sa.Column("resolution", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.PrimaryKeyConstraint("id", name="pk_recipe_flags"),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            ondelete="CASCADE",
            name="fk_recipe_flags_recipe_id_recipes",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_recipe_flags_resolved_by_users",
        ),
        sa.CheckConstraint(f"kind IN ({KINDS})", name=op.f("ck_recipe_flags_kind_known")),
        sa.CheckConstraint(
            "resolution IN ('fixed', 'dismissed')", name=op.f("ck_recipe_flags_resolution_known")
        ),
        # Open, or dealt with: never half of each.
        sa.CheckConstraint(
            "(resolved_at IS NULL) = (resolution IS NULL)",
            name=op.f("ck_recipe_flags_resolved_together"),
        ),
        sa.CheckConstraint("note <> ''", name=op.f("ck_recipe_flags_note_not_empty")),
    )
    op.create_index("ix_recipe_flags_recipe_id", "recipe_flags", ["recipe_id"])
    op.create_index(
        "ix_recipe_flags_open",
        "recipe_flags",
        ["created_at"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    kept = op.get_bind().execute(sa.text("SELECT count(*) FROM recipe_flags")).scalar_one()
    if kept:
        raise RuntimeError(
            f"{kept} recipe flag(s) exist, and the previous schema has nowhere to keep them."
            " Remove them first if losing them is intended."
        )
    op.drop_table("recipe_flags")
    op.drop_index("ix_recipes_created_by", "recipes")
    op.drop_constraint("fk_recipes_created_by_users", "recipes", type_="foreignkey")
    op.drop_column("recipes", "created_by")
