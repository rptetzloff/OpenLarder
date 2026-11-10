"""Proposed changes to a source's details as well as to a recipe.

*Ray, 2026-11-10: suggest changes to books.* A proposal is now of a recipe
(recipe_id) or of a source's title, subtitle, credits and editions
(source_id), never both.

Revision ID: 0044
Revises: 0043
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("proposals", sa.Column("source_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_proposals_source_id_sources"),
        "proposals",
        "sources",
        ["source_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_proposals_source_id"), "proposals", ["source_id"])
    op.alter_column("proposals", "recipe_id", nullable=True)
    op.create_check_constraint(
        op.f("ck_proposals_one_target"),
        "proposals",
        "(recipe_id IS NULL) <> (source_id IS NULL)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM proposals WHERE recipe_id IS NULL")
    op.drop_constraint(op.f("ck_proposals_one_target"), "proposals", type_="check")
    op.alter_column("proposals", "recipe_id", nullable=False)
    op.drop_index(op.f("ix_proposals_source_id"), table_name="proposals")
    op.drop_constraint(op.f("fk_proposals_source_id_sources"), "proposals", type_="foreignkey")
    op.drop_column("proposals", "source_id")
