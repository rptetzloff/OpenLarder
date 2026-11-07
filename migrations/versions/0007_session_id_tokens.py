"""Sessions keep the ID token, for signing out at the broker.

Authentik will send someone back after signing out only when the request
carries the ID token as id_token_hint. Sessions from before this migration
have none; signing out still ends the broker's session, without the return.

Downgrade drops the column. That loses nothing a user wrote: at worst, the
sessions open at the time sign out without being sent back here.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_sessions", sa.Column("id_token", sa.Text()))
    op.create_check_constraint(
        "ck_user_sessions_id_token_not_empty", "user_sessions", "id_token <> ''"
    )


def downgrade() -> None:
    op.drop_column("user_sessions", "id_token")
