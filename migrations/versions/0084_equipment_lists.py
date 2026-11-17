"""A person's own equipment: lists of what they have and want, shared with
household groups as a larder's lists are.

*Ray's equipment spec, 2026-11-15*, had one checklist a person
(`user_equipment`: a row for each thing they have), not shared. *Ray,
2026-11-15:* a household group shares it, as it shares a larder. *Ray,
2026-11-16*, asked how, the spec having no lists to share: "it should work
like larder and book lists work", and, asked which of the two, "Named
lists, like the larder". So these are the larder's three tables over again
(0046, 0047): lists a person names ("Kitchen", "Cabin"), each thing on one
by a name of their own and the piece of equipment it is, and the groups a
list is shared with.

The larder's things are have, running low or out; equipment doesn't run
low. *Ray, 2026-11-16*, asked what states it has: "Have / Want", as a book
on a shelf is. Something wanted stays on its list and doesn't count as had.

Private, like the larder: not in the edit history, the dumps or the API's
public reads, and gone with its owner's account.

Revision ID: 0084
Revises: 0083
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0084"
down_revision: str | None = "0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            name,
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        )
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "equipment_lists",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("name <> ''", name=op.f("ck_equipment_lists_name_not_empty")),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_equipment_lists_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_lists")),
    )
    op.create_index(op.f("ix_equipment_lists_owner_id"), "equipment_lists", ["owner_id"])
    op.create_table(
        "equipment_list_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("list_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("equipment_id", sa.UUID(), nullable=True),
        sa.Column("state", sa.Text(), server_default="have", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("name <> ''", name=op.f("ck_equipment_list_items_name_not_empty")),
        sa.CheckConstraint(
            "state IN ('have', 'want')", name=op.f("ck_equipment_list_items_state_known")
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["equipment_lists.id"],
            name=op.f("fk_equipment_list_items_list_id_equipment_lists"),
            ondelete="CASCADE",
        ),
        # A thing that goes (one a recipe brought in, when no recipe needs it
        # any more) leaves the item on its list, unmatched, as a larder's is.
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["equipment.id"],
            name=op.f("fk_equipment_list_items_equipment_id_equipment"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_list_items")),
    )
    op.create_index(op.f("ix_equipment_list_items_list_id"), "equipment_list_items", ["list_id"])
    op.create_index(
        op.f("ix_equipment_list_items_equipment_id"), "equipment_list_items", ["equipment_id"]
    )
    for table in ("equipment_lists", "equipment_list_items"):
        op.execute(
            f"CREATE TRIGGER {table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    op.create_table(
        "equipment_list_groups",
        sa.Column("list_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["equipment_lists.id"],
            name=op.f("fk_equipment_list_groups_list_id_equipment_lists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_equipment_list_groups_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("list_id", "group_id", name=op.f("pk_equipment_list_groups")),
    )
    op.create_index(
        op.f("ix_equipment_list_groups_group_id"), "equipment_list_groups", ["group_id"]
    )


def downgrade() -> None:
    op.drop_table("equipment_list_groups")
    op.drop_table("equipment_list_items")
    op.drop_table("equipment_lists")
