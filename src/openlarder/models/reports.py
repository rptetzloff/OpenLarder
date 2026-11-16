"""Reports of a problem with a public record (migration 0049,
routers/reports.py; equipment in 0083)."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, uuid_pk


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('recipe', 'source', 'ingredient', 'author', 'equipment')",
            name="target_kind_known",
        ),
        CheckConstraint(
            "reason IN ('wrong', 'duplicate', 'copied', 'spam', 'other', 'equipment')",
            name="reason_known",
        ),
        # "Equipment is wrong or missing" is said of a recipe: nothing else
        # has equipment recorded.
        CheckConstraint(
            "reason <> 'equipment' OR target_kind = 'recipe'", name="equipment_reason_on_recipe"
        ),
        CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="status_known"),
        Index("ix_reports_target", "target_kind", "target_id"),
        Index("ix_reports_open", "created_at", postgresql_where=text("status = 'open'")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # What it's about: a recipe, source, ingredient, author or piece of
    # equipment, by id (not a key, so a report outlives a merge; the queue
    # says when it's gone).
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    # Who sent it: an account, if signed in.
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # "user:<id>", or "ip:<pseudonym>" (usage.py): one open report each.
    reporter: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    # What the moderator did, or why not.
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
