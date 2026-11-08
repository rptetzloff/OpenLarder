"""Household groups: private family collections shared with family.

Family recipes, part 2 (TODO.md). A person makes a group and invites others
to it; each member has a role: view (sees what's shared with the group),
edit (also adds and changes recipes in it) or admin (also manages members
and invites). *Ray, 2026-11-08.* A collection's owner picks which of their
groups see it; joining a group shares nothing by itself (Ray).

An invite is for one person: it works once and expires after 7 days (Ray).
Only a hash of its token is kept, as for sessions.

Only a family collection can be shared: source_groups carries the source's
kind, and its composite key to sources (id, kind) only allows 'family'.

Revision ID: 0027
Revises: 0026
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
ROLES = "role IN ('view', 'edit', 'admin')"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _updated_at(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER {table}_updated_at BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_groups")),
        sa.CheckConstraint("name <> ''", name=op.f("ck_groups_name_not_empty")),
    )
    _updated_at("groups")

    op.create_table(
        "group_members",
        sa.Column("group_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("group_id", "user_id", name=op.f("pk_group_members")),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_group_members_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_group_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(ROLES, name=op.f("ck_group_members_role_known")),
    )
    op.create_index(op.f("ix_group_members_user_id"), "group_members", ["user_id"])
    _updated_at("group_members")

    op.create_table(
        "group_invites",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("group_id", UUID, nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_by", UUID),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("used_by", UUID),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_group_invites")),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_group_invites_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_group_invites_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["used_by"],
            ["users.id"],
            name=op.f("fk_group_invites_used_by_users"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("token_hash", name=op.f("uq_group_invites_token_hash")),
        sa.CheckConstraint(ROLES, name=op.f("ck_group_invites_role_known")),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_group_invites_token_hash_is_sha256")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_group_invites_expires_after_created")
        ),
        sa.CheckConstraint(
            "used_by IS NULL OR used_at IS NOT NULL",
            name=op.f("ck_group_invites_used_by_when_used"),
        ),
    )
    op.create_index(op.f("ix_group_invites_group_id"), "group_invites", ["group_id"])

    # A source's kind is part of the key, so only a family collection can be
    # shared.
    op.create_unique_constraint(op.f("uq_sources_id_kind"), "sources", ["id", "kind"])
    op.create_table(
        "source_groups",
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("kind", sa.Text(), server_default="family", nullable=False),
        sa.Column("group_id", UUID, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("source_id", "group_id", name=op.f("pk_source_groups")),
        sa.ForeignKeyConstraint(
            ["source_id", "kind"],
            ["sources.id", "sources.kind"],
            name=op.f("fk_source_groups_source_id_kind_sources"),
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_source_groups_group_id_groups"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("kind = 'family'", name=op.f("ck_source_groups_family_only")),
    )
    op.create_index(op.f("ix_source_groups_group_id"), "source_groups", ["group_id"])


def downgrade() -> None:
    op.drop_table("source_groups")
    op.drop_constraint(op.f("uq_sources_id_kind"), "sources", type_="unique")
    op.drop_table("group_invites")
    op.drop_table("group_members")
    op.drop_table("groups")
