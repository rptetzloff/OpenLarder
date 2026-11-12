"""Sharing a shelf with household groups.

*Ray, 2026-11-11: "a shelf should be shareable exactly the same way"* as a
larder list (0047): its owner chooses which of their groups see it; a view
member sees it, an edit or admin member changes what's on it. Sharing
stays its owner's.

Revision ID: 0063
Revises: 0062
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0063"
down_revision: str | None = "0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shelf_groups",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_shelf_groups_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_shelf_groups_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "group_id", name=op.f("pk_shelf_groups")),
    )
    op.create_index(op.f("ix_shelf_groups_group_id"), "shelf_groups", ["group_id"])


def downgrade() -> None:
    op.drop_table("shelf_groups")
