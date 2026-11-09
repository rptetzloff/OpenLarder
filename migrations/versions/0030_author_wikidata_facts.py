"""Facts about authors from Wikidata: born and died (years), country, website.

Wikidata is CC0, so its facts fit the catalog's ODbL; Wikipedia's prose
doesn't (SCOPING.md, Authors). wikidata_checked_at says when Wikidata was
last asked, so the admin page's catch-up asks for the authors never asked,
or not lately, first.

Revision ID: 0030
Revises: 0029
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("authors", sa.Column("born_year", sa.SmallInteger(), nullable=True))
    op.add_column("authors", sa.Column("died_year", sa.SmallInteger(), nullable=True))
    op.add_column("authors", sa.Column("country", sa.Text(), nullable=True))
    op.add_column("authors", sa.Column("website", sa.Text(), nullable=True))
    op.add_column(
        "authors", sa.Column("wikidata_checked_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    for column in ("wikidata_checked_at", "website", "country", "died_year", "born_year"):
        op.drop_column("authors", column)
