"""Display names are chosen in OpenLarder and unique, ignoring case.

display_name becomes the name a person chose, and is empty until they
choose one; the sign-in provider's name moves to suggested_name, kept only
to pre-fill that choice and cleared once it is made. Existing users have
chosen nothing yet, so their names move to suggested_name and they are
asked on their next visit. The old fallback, "OpenLarder user", is not
carried over as a suggestion.

Downgrade puts back a name for everyone, preferring the chosen one. It
drops suggested_name for people who have chosen, which loses nothing they
wrote.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHAPE = "char_length(display_name) BETWEEN 2 AND 32 AND display_name = btrim(display_name)"


def upgrade() -> None:
    op.add_column("users", sa.Column("suggested_name", sa.Text()))
    op.execute("UPDATE users SET suggested_name = NULLIF(display_name, 'OpenLarder user')")
    op.drop_constraint("ck_users_display_name_not_empty", "users", type_="check")
    op.alter_column("users", "display_name", nullable=True)
    op.execute("UPDATE users SET display_name = NULL")
    op.create_check_constraint("ck_users_display_name_shape", "users", SHAPE)
    op.create_check_constraint("ck_users_suggested_name_not_empty", "users", "suggested_name <> ''")
    op.create_index(
        "uq_users_display_name_lower",
        "users",
        [sa.text("lower(display_name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_display_name_lower", "users")
    op.drop_constraint("ck_users_suggested_name_not_empty", "users", type_="check")
    op.drop_constraint("ck_users_display_name_shape", "users", type_="check")
    op.execute(
        "UPDATE users SET display_name = COALESCE(display_name, suggested_name, 'OpenLarder user')"
    )
    op.alter_column("users", "display_name", nullable=False)
    op.create_check_constraint("ck_users_display_name_not_empty", "users", "display_name <> ''")
    op.drop_column("users", "suggested_name")
