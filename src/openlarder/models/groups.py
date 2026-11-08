"""Household groups, which private family collections are shared with
(migration 0027). The rules on who sees what are in visibility.py; joining,
roles and invites in routers/groups.py."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    PrimaryKeyConstraint,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, Timestamps, uuid_pk

ROLES = "role IN ('view', 'edit', 'admin')"


class Group(Timestamps, Base):
    """A household: people who share private family collections."""

    __tablename__ = "groups"
    __table_args__ = (CheckConstraint("name <> ''", name="name_not_empty"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)


class GroupMember(Timestamps, Base):
    """A person in a group. view: sees what's shared with it; edit: also adds
    and changes recipes in it; admin: also manages members and invites."""

    __tablename__ = "group_members"
    __table_args__ = (
        PrimaryKeyConstraint("group_id", "user_id"),
        CheckConstraint(ROLES, name="role_known"),
        Index("ix_group_members_user_id", "user_id"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)


class GroupInvite(Base):
    """A link inviting one person into a group with a role: it works once
    and expires. Only the token's SHA-256 is kept."""

    __tablename__ = "group_invites"
    __table_args__ = (
        CheckConstraint(ROLES, name="role_known"),
        CheckConstraint("octet_length(token_hash) = 32", name="token_hash_is_sha256"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint("used_by IS NULL OR used_at IS NOT NULL", name="used_by_when_used"),
        Index("ix_group_invites_group_id", "group_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class SourceGroup(Base):
    """A private family collection shared with a group. The source's kind is
    part of the key to sources, so only a family collection can be."""

    __tablename__ = "source_groups"
    __table_args__ = (
        PrimaryKeyConstraint("source_id", "group_id"),
        ForeignKeyConstraint(
            ["source_id", "kind"],
            ["sources.id", "sources.kind"],
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        CheckConstraint("kind = 'family'", name="family_only"),
        Index("ix_source_groups_group_id", "group_id"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="family")
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
