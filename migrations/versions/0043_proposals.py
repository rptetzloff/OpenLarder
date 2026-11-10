"""Proposed changes: a contributor suggests an edit to a published recipe,
and a moderator applies it or declines it.

*Ray, 2026-11-10: build review first; contributors' edits to published
records come after.* A proposal keeps the edit as the recipe form sends it,
the newest revision of the recipe when it was made (so a moderator is told
if the recipe has changed since), and why.

Revision ID: 0043
Revises: 0042
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposals",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("recipe_id", sa.UUID(), nullable=False),
        sa.Column("proposed_by", sa.UUID(), nullable=True),
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("based_on", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'applied', 'declined', 'withdrawn')",
            name=op.f("ck_proposals_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_proposals_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_by"],
            ["users.id"],
            name=op.f("fk_proposals_proposed_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_proposals_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposals")),
    )
    op.create_index(op.f("ix_proposals_recipe_id"), "proposals", ["recipe_id"])
    op.create_index(op.f("ix_proposals_proposed_by"), "proposals", ["proposed_by"])
    op.create_index(
        "ix_proposals_open",
        "proposals",
        ["created_at"],
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_table("proposals")
