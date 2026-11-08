"""Websites as sources, and recipes on their pages.

Step 2 of sources beyond books (TODO.md). A website is a source of kind
'website', one per site, found by its host ("smittenkitchen.com", without
"www."); a site behind a subscription is marked paywalled, and is linked,
never copied. A recipe on it is a web page: its address. *Ray, 2026-11-08.*

A recipe's location is now a place in an edition (a book's, with a page)
or a web page, never both, so recipe_locations gets its own id: its old key
was (recipe, edition). The composite keys still keep a location inside its
own source.

Downgrade refuses while any website or web page exists, rather than drop
them.

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_sources_kind_known"), "sources", type_="check")
    op.create_check_constraint(
        op.f("ck_sources_kind_known"), "sources", "kind IN ('book', 'website')"
    )
    op.add_column("sources", sa.Column("host", sa.Text()))
    op.add_column(
        "sources",
        sa.Column("paywalled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_sources_host_for_websites"), "sources", "(kind = 'website') = (host IS NOT NULL)"
    )
    op.create_check_constraint(op.f("ck_sources_host_not_empty"), "sources", "host <> ''")
    op.create_check_constraint(
        op.f("ck_sources_paywalled_websites_only"), "sources", "NOT paywalled OR kind = 'website'"
    )
    op.create_unique_constraint(op.f("uq_sources_host"), "sources", ["host"])

    op.create_table(
        "web_pages",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_web_pages")),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_web_pages_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("url", name=op.f("uq_web_pages_url")),
        # The target of recipe_locations' composite key.
        sa.UniqueConstraint("source_id", "id", name=op.f("uq_web_pages_source_id_id")),
        sa.CheckConstraint("url <> ''", name=op.f("ck_web_pages_url_not_empty")),
    )
    op.execute(
        "CREATE TRIGGER web_pages_updated_at BEFORE UPDATE ON web_pages "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.drop_constraint(op.f("pk_recipe_locations"), "recipe_locations", type_="primary")
    op.add_column(
        "recipe_locations",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
    )
    op.create_primary_key(op.f("pk_recipe_locations"), "recipe_locations", ["id"])
    op.alter_column("recipe_locations", "edition_id", nullable=True)
    op.add_column("recipe_locations", sa.Column("web_page_id", UUID))
    op.create_foreign_key(
        op.f("fk_recipe_locations_source_id_web_page_id_web_pages"),
        "recipe_locations",
        "web_pages",
        ["source_id", "web_page_id"],
        ["source_id", "id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        op.f("ck_recipe_locations_one_place"),
        "recipe_locations",
        "num_nonnulls(edition_id, web_page_id) = 1",
    )
    op.create_check_constraint(
        op.f("ck_recipe_locations_page_needs_edition"),
        "recipe_locations",
        "page IS NULL OR edition_id IS NOT NULL",
    )
    op.create_unique_constraint(
        op.f("uq_recipe_locations_recipe_id_edition_id"),
        "recipe_locations",
        ["recipe_id", "edition_id"],
    )
    op.create_unique_constraint(
        op.f("uq_recipe_locations_recipe_id_web_page_id"),
        "recipe_locations",
        ["recipe_id", "web_page_id"],
    )
    op.create_index(op.f("ix_recipe_locations_web_page_id"), "recipe_locations", ["web_page_id"])


def downgrade() -> None:
    bind = op.get_bind()
    held = bind.scalar(sa.text("SELECT count(*) FROM sources WHERE kind = 'website'"))
    if held:
        raise RuntimeError(f"{held} websites exist; remove them before downgrading.")
    op.drop_index(op.f("ix_recipe_locations_web_page_id"), "recipe_locations")
    for name in (
        "uq_recipe_locations_recipe_id_web_page_id",
        "uq_recipe_locations_recipe_id_edition_id",
    ):
        op.drop_constraint(op.f(name), "recipe_locations", type_="unique")
    for name in ("ck_recipe_locations_page_needs_edition", "ck_recipe_locations_one_place"):
        op.drop_constraint(op.f(name), "recipe_locations", type_="check")
    op.drop_constraint(
        op.f("fk_recipe_locations_source_id_web_page_id_web_pages"),
        "recipe_locations",
        type_="foreignkey",
    )
    op.drop_column("recipe_locations", "web_page_id")
    op.alter_column("recipe_locations", "edition_id", nullable=False)
    op.drop_constraint(op.f("pk_recipe_locations"), "recipe_locations", type_="primary")
    op.drop_column("recipe_locations", "id")
    op.create_primary_key(
        op.f("pk_recipe_locations"), "recipe_locations", ["recipe_id", "edition_id"]
    )

    op.drop_table("web_pages")

    op.drop_constraint(op.f("uq_sources_host"), "sources", type_="unique")
    for name in (
        "ck_sources_paywalled_websites_only",
        "ck_sources_host_not_empty",
        "ck_sources_host_for_websites",
    ):
        op.drop_constraint(op.f(name), "sources", type_="check")
    op.drop_column("sources", "paywalled")
    op.drop_column("sources", "host")
    op.drop_constraint(op.f("ck_sources_kind_known"), "sources", type_="check")
    op.create_check_constraint(op.f("ck_sources_kind_known"), "sources", "kind IN ('book')")
