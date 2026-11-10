"""How much programs outside the site use the API, a day at a time
(usage.py), for admins to watch for abuse. An address is never stored: a
caller without a key is a pseudonym (a keyed hash of its address) and its
network. Kept 30 days."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base


class ApiUsage(Base):
    __tablename__ = "api_usage"
    __table_args__ = (
        CheckConstraint("caller <> ''", name="caller_not_empty"),
        CheckConstraint("requests >= 0 AND searches >= 0 AND refused >= 0", name="counts_positive"),
    )

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    # "key:<id>", or "ip:<pseudonym>": a keyed hash of the address, the same
    # every day, which can't be turned back into the address.
    caller: Mapped[str] = mapped_column(Text, primary_key=True)
    # The key, while it exists.
    key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"), index=True
    )
    # Without a key: the address's network (203.0.113.0/24, 2001:db8:1::/48).
    network: Mapped[str | None] = mapped_column(Text)
    # Answered requests, of which searches; and those refused over a limit.
    requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    searches: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    refused: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
