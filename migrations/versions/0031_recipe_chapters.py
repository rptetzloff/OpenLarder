"""The chapter or section of its book a recipe is in ("Yeast Breads").

Each book names its own, so a chapter is text on the recipe, not a tag:
tags (course, cuisine, diet) are one list across the catalog. The household
index's Tag column is the chapter, imported from now on; running an import
again fills it in on the recipes it already added. *Ray, 2026-11-09.*

Revision ID: 0031
Revises: 0030
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("chapter", sa.Text(), nullable=True))
    op.create_check_constraint("chapter_not_empty", "recipes", "chapter <> ''")


def downgrade() -> None:
    op.drop_constraint("chapter_not_empty", "recipes", type_="check")
    op.drop_column("recipes", "chapter")
