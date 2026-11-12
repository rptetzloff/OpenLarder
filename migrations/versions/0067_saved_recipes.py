"""Saved recipes: the ones you want to cook, and the ones you have.

*SCOPING.md, "Saves, likes, 'want to cook' lists".* A recipe is saved as
wanted or cooked. Private, as the larder and shelf are: not catalog data,
so not in the edit history, the dumps or the API's public reads; shared
with household groups the same way (saved_groups), since a household plans
its cooking together.

Revision ID: 0067
Revises: 0066
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067"
down_revision: str | None = "0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _stamp(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "saved_recipes",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("recipe_id", sa.UUID(), nullable=False),
        sa.Column("state", sa.Text(), server_default="want", nullable=False),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.CheckConstraint(
            "state IN ('want', 'cooked')", name=op.f("ck_saved_recipes_state_known")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_saved_recipes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_saved_recipes_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "recipe_id", name=op.f("pk_saved_recipes")),
    )
    op.create_index(op.f("ix_saved_recipes_recipe_id"), "saved_recipes", ["recipe_id"])
    op.execute(
        "CREATE TRIGGER saved_recipes_updated_at BEFORE UPDATE ON saved_recipes "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_table(
        "saved_groups",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        _stamp("created_at"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_saved_groups_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_saved_groups_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "group_id", name=op.f("pk_saved_groups")),
    )
    op.create_index(op.f("ix_saved_groups_group_id"), "saved_groups", ["group_id"])


def downgrade() -> None:
    op.drop_table("saved_groups")
    op.drop_table("saved_recipes")
