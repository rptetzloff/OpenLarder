"""API keys: reading the public API at a higher rate.

Anyone may read the API without a key, at a low rate per address; a free
key, made on Your account, raises it. *Ray, 2026-11-09.* Only the key's
hash is kept, as with session tokens.

Revision ID: 0036
Revises: 0035
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("name <> ''", name=op.f("ck_api_keys_name_not_empty")),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_api_keys_token_hash_is_sha256")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_api_keys_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_api_keys_token_hash")),
    )
    op.create_index(op.f("ix_api_keys_user_id"), "api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_table("api_keys")
