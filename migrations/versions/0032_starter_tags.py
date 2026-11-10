"""The starter list of tags: course, cuisine and technique.

Tags come from a fixed list, one per kind, which only admins add to, so a
search filter never splits between "Gluten Free" and "gluten-free". *Ray,
2026-11-09.* This is the list to start from; admins add to it on the site.
Diets were started by migration 0018, for substitutions, and are the same
tags.

Revision ID: 0032
Revises: 0031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STARTER = {
    "course": [
        "Appetizer",
        "Bread",
        "Breakfast",
        "Dessert",
        "Drink",
        "Main",
        "Salad",
        "Sauce",
        "Side",
        "Snack",
        "Soup",
    ],
    "cuisine": [
        "American",
        "Chinese",
        "French",
        "Greek",
        "Indian",
        "Italian",
        "Japanese",
        "Korean",
        "Mediterranean",
        "Mexican",
        "Middle Eastern",
        "Spanish",
        "Thai",
        "Vietnamese",
    ],
    "technique": [
        "Baking",
        "Braising",
        "Fermenting",
        "Grilling",
        "No-Cook",
        "Pressure Cooker",
        "Roasting",
        "Slow Cooker",
        "Smoking",
        "Sous Vide",
    ],
}


def upgrade() -> None:
    insert = sa.text(
        "INSERT INTO tags (kind, name) VALUES (CAST(:kind AS tag_kind), :name)"
        " ON CONFLICT (kind, lower(name)) DO NOTHING"
    )
    for kind, names in STARTER.items():
        for name in names:
            op.get_bind().execute(insert, {"kind": kind, "name": name})


def downgrade() -> None:
    # Those something is tagged with stay.
    remove = sa.text(
        "DELETE FROM tags t WHERE t.kind = CAST(:kind AS tag_kind) AND t.name = :name"
        " AND NOT EXISTS (SELECT 1 FROM source_tags s WHERE s.tag_id = t.id)"
        " AND NOT EXISTS (SELECT 1 FROM recipe_tags r WHERE r.tag_id = t.id)"
    )
    for kind, names in STARTER.items():
        for name in names:
            op.get_bind().execute(remove, {"kind": kind, "name": name})
