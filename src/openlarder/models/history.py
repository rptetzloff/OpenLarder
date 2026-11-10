"""Edit history: a revision for every catalog row added, changed or
removed, written by a trigger (migration 0040), never by the app. history.py
reads it, and decides who may. *Ray, 2026-11-10.*"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base


class Revision(Base):
    __tablename__ = "revisions"
    __table_args__ = (
        CheckConstraint("action IN ('i', 'u', 'd')", name="action_known"),
        Index("ix_revisions_record", "table_name", "record_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # One save: everything a request (or an import batch) wrote together.
    change_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Who, if it came through the app signed in.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # What it came through: "import:<run>", "suggestion:<id>", ...
    via: Mapped[str | None] = mapped_column(Text)
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # i(nsert), u(pdate), d(elete).
    action: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    # The ingredient or author a row hangs off (aliases, links, options).
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    # In a family collection, or where it belongs isn't known: never shown
    # without checking the collection can be seen.
    family: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # {column: [before, after]}; only what changed.
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False)
