"""Weekly ODbL data dumps: each one built, where its files are, and what's
in them (dumps.py). *Ray, 2026-11-10: object storage; CSV and JSON Lines.*

Revision ID: 0045
Revises: 0044
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dumps",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "built_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("csv_key", sa.Text(), nullable=False),
        sa.Column("csv_bytes", sa.BigInteger(), nullable=False),
        sa.Column("json_key", sa.Text(), nullable=False),
        sa.Column("json_bytes", sa.BigInteger(), nullable=False),
        sa.Column("counts", postgresql.JSONB(), nullable=False),
        sa.Column("built_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["built_by"], ["users.id"], name=op.f("fk_dumps_built_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dumps")),
    )
    op.create_index(op.f("ix_dumps_built_at"), "dumps", ["built_at"])


def downgrade() -> None:
    op.drop_table("dumps")
