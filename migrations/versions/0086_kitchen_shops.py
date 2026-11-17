"""Shops for equipment, and the clicks on their links.

*Ray's equipment spec, 2026-11-15, Part 8.* The shops table takes a fourth
kind, `kitchen`, beside the booksellers, grocers and producers: where a
piece of equipment's Shop link goes, a search at the shop for it (its
shopping term, or its name), through /go/equipment/<shop>/<equipment>.

`equipment_clicks` is the grocery clicks' table over again (0058): which
piece of equipment, which shop, when, and from which OpenLarder page;
nothing about who clicked.

One shop is seeded, Amazon, with the Associates tag its bookseller row has
today, and switched off: it sends nobody anywhere until an administrator
switches it on, on the Shops page. Whether these links should earn under
the books' tag or one of their own is theirs to say there.

Revision ID: 0086
Revises: 0085
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0086"
down_revision: str | None = "0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = "kind IN ('bookseller', 'grocer', 'producer')"
AFTER = "kind IN ('bookseller', 'grocer', 'producer', 'kitchen')"
AMAZON_NOTE = "As an Amazon Associate, OpenLarder earns from qualifying purchases."


def upgrade() -> None:
    op.drop_constraint(op.f("ck_shops_kind_known"), "shops", type_="check")
    op.create_check_constraint(op.f("ck_shops_kind_known"), "shops", AFTER)
    op.create_table(
        "equipment_clicks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("equipment_id", sa.UUID(), nullable=False),
        sa.Column("shop", sa.Text(), nullable=False),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("shop <> ''", name=op.f("ck_equipment_clicks_shop_not_empty")),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["equipment.id"],
            name=op.f("fk_equipment_clicks_equipment_id_equipment"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_clicks")),
    )
    op.create_index("ix_equipment_clicks_clicked_at", "equipment_clicks", ["clicked_at"])
    op.create_index("ix_equipment_clicks_equipment_id", "equipment_clicks", ["equipment_id"])
    # Not an edit, so not in the edit history (0074's trigger), as 0076's
    # copying wasn't: a database as it's made has no history, and the shop
    # as it's seeded is nobody's change.
    op.execute("ALTER TABLE shops DISABLE TRIGGER record_revision")
    seed(op.get_bind())
    op.execute("ALTER TABLE shops ENABLE TRIGGER record_revision")


def seed(connection) -> None:
    """Amazon as a kitchen shop, switched off. The tag is copied if the
    bookseller has one; with none, the row is there to be given one."""
    connection.execute(
        sa.text(
            "INSERT INTO shops (kind, key, label, builder, affiliate_id, earns, note, enabled,"
            " position)"
            " VALUES ('kitchen', 'amazon', 'Amazon', 'amazon',"
            " (SELECT affiliate_id FROM shops WHERE kind = 'bookseller' AND key = 'amazon'),"
            " 'affiliate', :note, false, 0)"
        ),
        {"note": AMAZON_NOTE},
    )


def downgrade() -> None:
    op.execute("DELETE FROM shops WHERE kind = 'kitchen'")
    op.drop_table("equipment_clicks")
    op.drop_constraint(op.f("ck_shops_kind_known"), "shops", type_="check")
    op.create_check_constraint(op.f("ck_shops_kind_known"), "shops", BEFORE)
