"""Proposed changes to published recipes (migration 0043,
routers/proposals.py). *Ray, 2026-11-10.*"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, uuid_pk


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'applied', 'declined', 'withdrawn')", name="status_known"
        ),
        CheckConstraint("(recipe_id IS NULL) <> (source_id IS NULL)", name="one_target"),
        Index("ix_proposals_open", "created_at", postgresql_where=text("status = 'open'")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # What it's for: a recipe, or a source's own details (migration 0044).
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # The edit as the form sends it (routers/recipes.RecipeIn, or
    # routers/sources.BookIn).
    body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Why, in the contributor's words.
    reason: Mapped[str | None] = mapped_column(Text)
    # The recipe's newest revision when it was proposed; a later one means
    # it has changed since.
    based_on: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    # Why it was declined.
    note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
