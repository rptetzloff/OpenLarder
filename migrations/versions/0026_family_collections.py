"""Family recipe collections, which can be private.

Step 6 of sources beyond books (TODO.md). A family collection (a recipe box,
a church cookbook, a class's handouts) is a source with an owner: the person
who added it. It is private or public as a whole (Ray, 2026-11-08: the
collection, not each recipe). Private means seen only by its owner, until
household groups arrive. Adding one records when the person ticked that they
understand what the site keeps and who sees it.

Only a family collection has an owner or can be private; every family
collection has both an owner and that acknowledgement. Its recipes are
simply in it, with no page, as packaging's are.

The owner is kept from deletion (RESTRICT) rather than taking the
collection with them, until deleting an account is designed.

Downgrade refuses while any family collection exists, rather than drop them.

Revision ID: 0026
Revises: 0025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = (
    "'book', 'website', 'magazine', 'newspaper', 'tv_show', 'podcast', 'video_channel',"
    " 'social', 'packaging'"
)


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_sources_kind_known"), "sources", type_="check")
    op.create_check_constraint(op.f("ck_sources_kind_known"), "sources", f"kind IN ({kinds})")


def upgrade() -> None:
    _kinds(f"{BEFORE}, 'family'")
    op.add_column("sources", sa.Column("owner_id", pg.UUID(as_uuid=True)))
    op.add_column(
        "sources", sa.Column("private", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.add_column("sources", sa.Column("acknowledged_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        op.f("fk_sources_owner_id_users"),
        "sources",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_sources_owner_id"), "sources", ["owner_id"])
    op.create_check_constraint(
        op.f("ck_sources_owner_for_family"), "sources", "(kind = 'family') = (owner_id IS NOT NULL)"
    )
    op.create_check_constraint(
        op.f("ck_sources_private_only_family"), "sources", "NOT private OR kind = 'family'"
    )
    op.create_check_constraint(
        op.f("ck_sources_family_acknowledged"),
        "sources",
        "(kind = 'family') = (acknowledged_at IS NOT NULL)",
    )


def downgrade() -> None:
    held = op.get_bind().scalar(sa.text("SELECT count(*) FROM sources WHERE kind = 'family'"))
    if held:
        raise RuntimeError(f"{held} family collections exist; remove them before downgrading.")
    op.drop_constraint(op.f("ck_sources_family_acknowledged"), "sources", type_="check")
    op.drop_constraint(op.f("ck_sources_private_only_family"), "sources", type_="check")
    op.drop_constraint(op.f("ck_sources_owner_for_family"), "sources", type_="check")
    op.drop_index(op.f("ix_sources_owner_id"), "sources")
    op.drop_constraint(op.f("fk_sources_owner_id_users"), "sources", type_="foreignkey")
    op.drop_column("sources", "acknowledged_at")
    op.drop_column("sources", "private")
    op.drop_column("sources", "owner_id")
    _kinds(BEFORE)
