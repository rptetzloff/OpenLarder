"""Requests for books to be indexed, their votes, and the enterer role.

*Ray, 2026-11-09:* anyone asks for a cookbook or another source to be
entered; enterers, a role admins grant, claim requests and queue them up;
a claim lapses after 30 days with nothing done.

Revision ID: 0038
Revises: 0037
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_enterer", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_table(
        "book_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("isbn13", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("votes", sa.Integer(), server_default="1", nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("claimed_by", sa.UUID(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.CheckConstraint("title <> ''", name=op.f("ck_book_requests_title_not_empty")),
        sa.CheckConstraint(
            "status IN ('open', 'claimed', 'done', 'declined')",
            name=op.f("ck_book_requests_status_known"),
        ),
        sa.CheckConstraint("votes >= 1", name=op.f("ck_book_requests_votes_positive")),
        sa.CheckConstraint(
            "(status = 'claimed') = (claimed_by IS NOT NULL)",
            name=op.f("ck_book_requests_claimed_has_claimer"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_book_requests_source_id_sources"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_book_requests_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["claimed_by"],
            ["users.id"],
            name=op.f("fk_book_requests_claimed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_book_requests")),
    )
    op.create_index(
        "uq_book_requests_isbn_open",
        "book_requests",
        ["isbn13"],
        unique=True,
        postgresql_where=sa.text("status IN ('open', 'claimed') AND isbn13 IS NOT NULL"),
    )
    op.create_index("ix_book_requests_status_votes", "book_requests", ["status", "votes"])
    for column in ("source_id", "requested_by", "claimed_by"):
        op.create_index(op.f(f"ix_book_requests_{column}"), "book_requests", [column])
    op.create_table(
        "request_votes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("voter", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["book_requests.id"],
            name=op.f("fk_request_votes_request_id_book_requests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_votes")),
        sa.UniqueConstraint("request_id", "voter", name=op.f("uq_request_votes_request_id_voter")),
    )


def downgrade() -> None:
    op.drop_table("request_votes")
    op.drop_table("book_requests")
    op.drop_column("users", "is_enterer")
