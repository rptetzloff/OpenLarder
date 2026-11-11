"""A record of each merge of two books (book_merge.py), so an administrator
can take one apart again. *Ray, 2026-11-11: a check on moderators.*

The edit history records most of a merge, but not all: requests and
proposals aren't in it, and a tag moved between books is recorded without
saying which tag. So the merge keeps what it moved here."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, uuid_pk


class BookMerge(Base):
    __tablename__ = "book_merges"
    __table_args__ = (
        CheckConstraint("gone_title <> ''", name="gone_title_not_empty"),
        Index("ix_book_merges_merged_at", "merged_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # The book removed, which an unmerge puts back under the same id.
    gone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    gone_title: Mapped[str] = mapped_column(Text, nullable=False)
    # The book kept. Not a key: if it's merged on into a third, this record
    # stays, to be undone once that one is.
    kept_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    merged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    merged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # What moved, and the removed book's row (book_merge.Saved).
    saved: Mapped[dict] = mapped_column(JSONB, nullable=False)
    undone_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
