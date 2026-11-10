"""Roles: user, contributor, moderator, admin and owner, in place of
is_admin and is_enterer.

*Ray, 2026-11-10.* Admins stay admins and enterers become contributors.
No one is made owner here: that's set in the database by hand (roles.py).

Revision ID: 0039
Revises: 0038
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.Text(), server_default="user", nullable=False))
    op.execute(
        "UPDATE users SET role = CASE WHEN is_admin THEN 'admin' ELSE 'contributor' END"
        " WHERE is_admin OR is_enterer"
    )
    op.create_check_constraint(
        op.f("ck_users_role_known"),
        "users",
        "role IN ('user', 'contributor', 'moderator', 'admin', 'owner')",
    )
    op.drop_column("users", "is_enterer")
    op.drop_column("users", "is_admin")


def downgrade() -> None:
    op.add_column(
        "users", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.add_column(
        "users", sa.Column("is_enterer", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.execute(
        "UPDATE users SET is_admin = role IN ('moderator', 'admin', 'owner'),"
        " is_enterer = role = 'contributor'"
    )
    op.drop_constraint(op.f("ck_users_role_known"), "users", type_="check")
    op.drop_column("users", "role")
