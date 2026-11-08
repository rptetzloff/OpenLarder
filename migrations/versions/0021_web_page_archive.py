"""The Internet Archive's copy of a web recipe's page.

When a web recipe is added, the Archive is asked to capture its page
(archive.py), and the copy's address and date are kept here, with when one
was last asked for. An admin marks a page gone when it no longer has the
recipe; the copy is offered instead. *Ray, 2026-11-08.*

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("web_pages", sa.Column("archive_url", sa.Text()))
    op.add_column("web_pages", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("web_pages", sa.Column("archive_tried_at", sa.DateTime(timezone=True)))
    op.add_column(
        "web_pages", sa.Column("gone", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.create_check_constraint(
        op.f("ck_web_pages_archive_url_not_empty"), "web_pages", "archive_url <> ''"
    )
    op.create_check_constraint(
        op.f("ck_web_pages_archived_together"),
        "web_pages",
        "(archive_url IS NULL) = (archived_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_web_pages_archived_together"), "web_pages", type_="check")
    op.drop_constraint(op.f("ck_web_pages_archive_url_not_empty"), "web_pages", type_="check")
    for column in ("gone", "archive_tried_at", "archived_at", "archive_url"):
        op.drop_column("web_pages", column)
