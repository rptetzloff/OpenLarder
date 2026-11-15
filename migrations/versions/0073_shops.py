"""Shops in a table of their own: the booksellers and the grocers.

*Decided by Ray, 2026-11-13* (round 4, part D): each shop's affiliate
setting was an environment variable, so adding or changing one meant
editing Coolify and redeploying. They move to a table an administrator
will edit from the site. This is the table, and the shops there are today,
with each one's setting copied from the variable it's in now and the shop
switched on where that's set. Nothing a visitor sees changes: the links,
the /go/ addresses and the click records are as they were.

A shop's key is unique among its kind, not among every shop: Amazon is a
bookseller and Amazon Fresh a grocer, both "amazon", at /go/amazon/… and
/go/grocer/amazon/…, and both addresses are already on the web.

The variables are read here from the environment, not through the app's
settings: a migration says what it did when it ran, whatever the app
becomes later. Where one isn't set as this runs (a test database, a
variable added afterwards), the row is seeded switched off with no value,
and for one release the app still reads the variable for a row nobody has
changed (shops.py).

Revision ID: 0073
Revises: 0072
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0073"
down_revision: str | None = "0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AMAZON_NOTE = "As an Amazon Associate, OpenLarder earns from qualifying purchases."
# kind, key, label, builder, which column the setting fills, the variable it's
# in today, the shop's own address, format, note; in the order pages show them.
SHOPS = [
    ("bookseller", "bookshop", "Bookshop.org", "bookshop", "affiliate_id",
     "BOOKSHOP_AFFILIATE_ID", "https://bookshop.org/a/{id}/{isbn13}", "print", None),
    ("bookseller", "bn", "Barnes & Noble", "wrapped", "wrapper_template",
     "BARNES_NOBLE_LINK", "https://www.barnesandnoble.com/w/?ean={isbn13}", "print", None),
    ("bookseller", "thriftbooks", "ThriftBooks", "wrapped", "wrapper_template",
     "THRIFTBOOKS_LINK", "https://www.thriftbooks.com/browse/?b.search={isbn13}", "print", None),
    ("bookseller", "bookoutlet", "Book Outlet", "wrapped", "wrapper_template",
     "BOOKOUTLET_LINK", "https://bookoutlet.com/search?q={isbn13}", "print", None),
    # Its address is made in code: an ISBN-10 where there is one, a search
    # where there isn't.
    ("bookseller", "amazon", "Amazon", "amazon", "affiliate_id",
     "AMAZON_TAG", None, "print", AMAZON_NOTE),
    # An ebook has an ISBN of its own, so Kobo is searched by title and author.
    ("bookseller", "kobo", "Kobo", "wrapped", "wrapper_template",
     "KOBO_LINK", "https://www.kobo.com/us/en/search?query={words}", "ebook", None),
    ("grocer", "instacart", "Instacart", "wrapped", "wrapper_template",
     "INSTACART_LINK", "https://www.instacart.com/store/s?k={term}", None, None),
    ("grocer", "amazon", "Amazon Fresh", "amazon", "affiliate_id",
     "AMAZON_TAG", None, None, AMAZON_NOTE),
    ("grocer", "walmart", "Walmart", "wrapped", "wrapper_template",
     "WALMART_LINK", "https://www.walmart.com/search?q={term}", None, None),
]  # fmt: skip


def seeded(environ) -> list[dict]:
    """A row for each shop there is today, with its setting from the variable
    it's in and switched on where that's set."""
    rows, places = [], {}
    for kind, key, label, builder, column, variable, product, format_, note in SHOPS:
        value = (environ.get(f"OPENLARDER_{variable}") or "").strip() or None
        places[kind] = places.get(kind, -1) + 1
        rows.append(
            {
                "key": key,
                "kind": kind,
                "label": label,
                "builder": builder,
                "affiliate_id": value if column == "affiliate_id" else None,
                "wrapper_template": value if column == "wrapper_template" else None,
                "product_template": product,
                "format": format_,
                "note": note,
                "enabled": value is not None,
                "position": places[kind],
            }
        )
    return rows


def upgrade() -> None:
    shops = op.create_table(
        "shops",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("builder", sa.Text(), nullable=False),
        sa.Column("affiliate_id", sa.Text(), nullable=True),
        sa.Column("wrapper_template", sa.Text(), nullable=True),
        sa.Column("product_template", sa.Text(), nullable=True),
        sa.Column("format", sa.Text(), nullable=True),
        sa.Column("earns", sa.Text(), server_default="affiliate", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("offer", sa.Text(), nullable=True),
        sa.Column("ships_to", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('bookseller', 'grocer', 'producer')", name=op.f("ck_shops_kind_known")
        ),
        sa.CheckConstraint(
            "builder IN ('bookshop', 'amazon', 'wrapped', 'template', 'direct')",
            name=op.f("ck_shops_builder_known"),
        ),
        sa.CheckConstraint("format IN ('print', 'ebook')", name=op.f("ck_shops_format_known")),
        sa.CheckConstraint(
            "earns IN ('affiliate', 'referral', 'none')", name=op.f("ck_shops_earns_known")
        ),
        sa.CheckConstraint("key ~ '^[a-z0-9-]+$'", name=op.f("ck_shops_key_shape")),
        sa.CheckConstraint("label <> ''", name=op.f("ck_shops_label_not_empty")),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_shops_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shops")),
        sa.UniqueConstraint("kind", "key", name=op.f("uq_shops_kind_key")),
    )
    op.bulk_insert(shops, seeded(os.environ))


def downgrade() -> None:
    op.drop_table("shops")
