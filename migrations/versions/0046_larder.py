"""The personal larder: each person's own lists of what they have, each
item matched to an ingredient, for "what can I make with what I have".

*Ray, 2026-11-08 and 2026-11-10:* lists named their own way ("Pantry",
"Spice drawer"); an item is a name of their own ("Cholula Chipotle") and
the ingredient it is (Chipotle Hot Sauce), which counts upward through the
hierarchy (it's hot sauce too); have, running low, or out, with no
amounts; private, and shared later through household groups. Not catalog
data: not in the edit history, the dumps or the API's public reads.

Revision ID: 0046
Revises: 0045
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "larder_lists",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("name <> ''", name=op.f("ck_larder_lists_name_not_empty")),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_larder_lists_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_larder_lists")),
    )
    op.create_index(op.f("ix_larder_lists_owner_id"), "larder_lists", ["owner_id"])
    op.create_table(
        "larder_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("list_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("ingredient_id", sa.UUID(), nullable=True),
        sa.Column("state", sa.Text(), server_default="have", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("name <> ''", name=op.f("ck_larder_items_name_not_empty")),
        sa.CheckConstraint(
            "state IN ('have', 'low', 'out')", name=op.f("ck_larder_items_state_known")
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["larder_lists.id"],
            name=op.f("fk_larder_items_list_id_larder_lists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_larder_items_ingredient_id_ingredients"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_larder_items")),
    )
    op.create_index(op.f("ix_larder_items_list_id"), "larder_items", ["list_id"])
    op.create_index(op.f("ix_larder_items_ingredient_id"), "larder_items", ["ingredient_id"])
    for table in ("larder_lists", "larder_items"):
        op.execute(
            f"CREATE TRIGGER {table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    op.drop_table("larder_items")
    op.drop_table("larder_lists")
