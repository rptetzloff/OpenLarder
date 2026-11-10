"""Requests for a cookbook, or another source, to be indexed (routers/
book_requests.py). *Ray, 2026-11-09:* anyone asks; contributors and up
(roles.py) claim a request and queue it up; a claim lapses after 30 days with
nothing done, and doesn't stop anyone entering the book sooner."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint

from openlarder.models.base import Base, uuid_pk


class BookRequest(Base):
    __tablename__ = "book_requests"
    __table_args__ = (
        CheckConstraint("title <> ''", name="title_not_empty"),
        CheckConstraint("status IN ('open', 'claimed', 'done', 'declined')", name="status_known"),
        CheckConstraint("votes >= 1", name="votes_positive"),
        CheckConstraint(
            "(status = 'claimed') = (claimed_by IS NOT NULL)", name="claimed_has_claimer"
        ),
        # One open request per ISBN; a second asks becomes a vote.
        Index(
            "uq_book_requests_isbn_open",
            "isbn13",
            unique=True,
            postgresql_where=text("status IN ('open', 'claimed') AND isbn13 IS NOT NULL"),
        ),
        Index("ix_book_requests_status_votes", "status", "votes"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    isbn13: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    # The source it's for, once it's in the catalog.
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    votes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The claim's last sign of life: claimed, or work done on it. A claim
    # quiet for CLAIM_LAPSES is open again.
    active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why it was declined.
    reason: Mapped[str | None] = mapped_column(Text)


class RequestVote(Base):
    """One voice per person, or per address, on a request. An address is
    stored only as its pseudonym (usage.py)."""

    __tablename__ = "request_votes"
    __table_args__ = (UniqueConstraint("request_id", "voter"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("book_requests.id", ondelete="CASCADE"), nullable=False
    )
    # "user:<id>" or "ip:<pseudonym>".
    voter: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
