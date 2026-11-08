"""Social media accounts and products' packaging as sources.

Step 5 of sources beyond books (TODO.md). A social media account is one
generic kind, not a kind per platform (Ray, 2026-11-08); its recipes are on
its posts, which are web pages by address, archived as a website's are. A
product's packaging is a source whose recipes are simply on it: there is no
page, issue or episode, so its recipes have no location rows.

Downgrade refuses while any account or product exists, rather than drop
them.

Revision ID: 0025
Revises: 0024
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = "'book', 'website', 'magazine', 'newspaper', 'tv_show', 'podcast', 'video_channel'"


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_sources_kind_known"), "sources", type_="check")
    op.create_check_constraint(op.f("ck_sources_kind_known"), "sources", f"kind IN ({kinds})")


def upgrade() -> None:
    _kinds(f"{BEFORE}, 'social', 'packaging'")


def downgrade() -> None:
    held = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM sources WHERE kind IN ('social', 'packaging')")
    )
    if held:
        raise RuntimeError(
            f"{held} social media accounts or products exist; remove them before downgrading."
        )
    _kinds(BEFORE)
