"""Notes on recipes: your own words about one, kept to yourself or shared
with household groups.

*Ray, 2026-11-11: "more than reviews... notes.... that are kept personal
(or shared)".* One note per person per recipe. Each note says which of its
writer's groups see it, as a larder list does; none, by default. Private:
not catalog data, so not in the edit history, the dumps or the API's
public reads, and never shown to moderators or administrators as such.

Revision ID: 0069
Revises: 0068
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069"
down_revision: str | None = "0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _stamp(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "recipe_notes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("recipe_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.CheckConstraint("body <> ''", name=op.f("ck_recipe_notes_body_not_empty")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recipe_notes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_notes_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_notes")),
        sa.UniqueConstraint("user_id", "recipe_id", name=op.f("uq_recipe_notes_user_id_recipe_id")),
    )
    op.create_index(op.f("ix_recipe_notes_recipe_id"), "recipe_notes", ["recipe_id"])
    op.execute(
        "CREATE TRIGGER recipe_notes_updated_at BEFORE UPDATE ON recipe_notes "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_table(
        "recipe_note_groups",
        sa.Column("note_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        _stamp("created_at"),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["recipe_notes.id"],
            name=op.f("fk_recipe_note_groups_note_id_recipe_notes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_recipe_note_groups_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("note_id", "group_id", name=op.f("pk_recipe_note_groups")),
    )
    op.create_index(op.f("ix_recipe_note_groups_group_id"), "recipe_note_groups", ["group_id"])


def downgrade() -> None:
    op.drop_table("recipe_note_groups")
    op.drop_table("recipe_notes")
