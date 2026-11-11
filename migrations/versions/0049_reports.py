"""Reports: anyone points a moderator at a problem with a public record.

*Ray, 2026-11-10: anyone, on any public record.* A report names a recipe,
source, ingredient or author, a reason (wrong, a duplicate, copied text,
spam, something else) and a note, and who sent it: an account, or, signed
out, the address's pseudonym (usage.py), never the address. Moderators
resolve or dismiss each, saying why.

Revision ID: 0049
Revises: 0048
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reporter_id", sa.UUID(), nullable=True),
        sa.Column("reporter", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_kind IN ('recipe', 'source', 'ingredient', 'author')",
            name=op.f("ck_reports_target_kind_known"),
        ),
        sa.CheckConstraint(
            "reason IN ('wrong', 'duplicate', 'copied', 'spam', 'other')",
            name=op.f("ck_reports_reason_known"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'dismissed')", name=op.f("ck_reports_status_known")
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["users.id"],
            name=op.f("fk_reports_reporter_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name=op.f("fk_reports_resolved_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )
    op.create_index("ix_reports_target", "reports", ["target_kind", "target_id"])
    op.create_index(op.f("ix_reports_reporter_id"), "reports", ["reporter_id"])
    op.create_index(
        "ix_reports_open", "reports", ["created_at"], postgresql_where=sa.text("status = 'open'")
    )


def downgrade() -> None:
    op.drop_table("reports")
