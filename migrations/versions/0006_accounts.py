"""Accounts: users, one per identity at the broker, and their sessions.

Downgrade refuses while any user exists, rather than drop them.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        _created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("issuer", "subject", name="uq_users_issuer_subject"),
        sa.CheckConstraint("issuer <> ''", name="ck_users_issuer_not_empty"),
        sa.CheckConstraint("subject <> ''", name="ck_users_subject_not_empty"),
        sa.CheckConstraint("display_name <> ''", name="ck_users_display_name_not_empty"),
    )
    op.execute(
        "CREATE TRIGGER users_updated_at BEFORE UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        _created_at(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_user_sessions_user_id_users"
        ),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name="ck_user_sessions_token_hash_is_sha256"
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_user_sessions_expires_after_created"
        ),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])


def downgrade() -> None:
    kept = op.get_bind().execute(sa.text("SELECT count(*) FROM users")).scalar_one()
    if kept:
        raise RuntimeError(
            f"{kept} user(s) exist, and the previous schema has nowhere to keep them."
            " Remove them first if losing them is intended."
        )
    op.drop_table("user_sessions")
    op.drop_table("users")
