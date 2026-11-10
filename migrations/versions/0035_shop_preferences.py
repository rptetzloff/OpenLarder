"""Each person's buy-link shops: the order they want them in, and those hidden.

People choose their shops on a book's page; signed in, the choice is kept
here and follows them; signed out, their browser keeps it. One shop at
least always shows. *Ray, 2026-11-09.*

Revision ID: 0035
Revises: 0034
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("shop_preferences", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "shop_preferences")
