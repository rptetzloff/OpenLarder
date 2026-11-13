"""The sulphites allergen reads "Sulfites".

The interface is in American spelling (*Ray's round 2 spec, 2026-11-13*),
and this label is shown on ingredients' and recipes' pages. Only the
label: the key stays 'sulphites', which the API, the dumps and the rules
name it by. A label a moderator has changed since isn't touched.

Revision ID: 0072
Revises: 0071
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0072"
down_revision: str | None = "0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE allergens SET label = 'Sulfites' WHERE key = 'sulphites' AND label = 'Sulphites'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE allergens SET label = 'Sulphites' WHERE key = 'sulphites' AND label = 'Sulfites'"
    )
