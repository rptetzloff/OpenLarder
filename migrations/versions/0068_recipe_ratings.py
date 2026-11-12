"""Ratings: one to five spoons on a recipe, from anyone signed in.

*Ray, 2026-11-11: "star ratings or similar... spoons or forks or
salamanders".* Spoons. One rating per person per recipe, changed or
cleared at will. A recipe shows the average and how many gave it, never
who: not catalog data, so not in the edit history or the dumps.

Revision ID: 0068
Revises: 0067
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0068"
down_revision: str | None = "0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _stamp(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "recipe_ratings",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("recipe_id", sa.UUID(), nullable=False),
        sa.Column("spoons", sa.SmallInteger(), nullable=False),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.CheckConstraint("spoons BETWEEN 1 AND 5", name=op.f("ck_recipe_ratings_spoons_range")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recipe_ratings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_ratings_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "recipe_id", name=op.f("pk_recipe_ratings")),
    )
    op.create_index(op.f("ix_recipe_ratings_recipe_id"), "recipe_ratings", ["recipe_id"])
    op.execute(
        "CREATE TRIGGER recipe_ratings_updated_at BEFORE UPDATE ON recipe_ratings "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.drop_table("recipe_ratings")
