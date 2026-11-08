"""A starting list of diets, for substitutions to serve.

A substitution usually stands in for something a diet rules out ("coconut
oil for butter, dairy-free"). Diets are tags of kind 'diet'. These start
the list; admins add others from the swap form when a book needs one.
*Ray, 2026-11-08.* They are reference data rather than entries, so the
pre-launch catalog reset should keep them.

Downgrade removes the seeded diets no substitution or tag link uses, and
leaves the rest.

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIETS = (
    "Gluten-Free",
    "Dairy-Free",
    "Egg-Free",
    "Nut-Free",
    "Soy-Free",
    "Vegan",
    "Vegetarian",
    "Paleo",
    "AIP",
    "Low-FODMAP",
)


def upgrade() -> None:
    for name in DIETS:
        op.get_bind().execute(
            sa.text(
                "INSERT INTO tags (kind, name) VALUES ('diet', :n)"
                " ON CONFLICT (kind, lower(name)) DO NOTHING"
            ),
            {"n": name},
        )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "DELETE FROM tags t WHERE t.kind = 'diet' AND t.name = ANY(:names)"
            " AND NOT EXISTS (SELECT 1 FROM substitutions s WHERE s.diet_tag_id = t.id)"
            " AND NOT EXISTS (SELECT 1 FROM work_tags w WHERE w.tag_id = t.id)"
            " AND NOT EXISTS (SELECT 1 FROM recipe_tags r WHERE r.tag_id = t.id)"
        ),
        {"names": list(DIETS)},
    )
