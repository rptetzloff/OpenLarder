"""Sharing larder lists with household groups.

*Ray, 2026-11-10: through household groups.* As for private family
collections (0027): a list's owner chooses which of their groups see it;
a view member sees it, an edit or admin member changes what's on it.
Renaming, removing and sharing a list stay its owner's.

Revision ID: 0047
Revises: 0046
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "larder_list_groups",
        sa.Column("list_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["larder_lists.id"],
            name=op.f("fk_larder_list_groups_list_id_larder_lists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_larder_list_groups_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("list_id", "group_id", name=op.f("pk_larder_list_groups")),
    )
    op.create_index(op.f("ix_larder_list_groups_group_id"), "larder_list_groups", ["group_id"])


def downgrade() -> None:
    op.drop_table("larder_list_groups")
