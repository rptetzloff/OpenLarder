"""The weekly ODbL data dumps (migration 0045, dumps.py)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, uuid_pk


class Dump(Base):
    __tablename__ = "dumps"

    id: Mapped[uuid.UUID] = uuid_pk()
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Where each file is in the bucket, and how big.
    csv_key: Mapped[str] = mapped_column(Text, nullable=False)
    csv_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    json_key: Mapped[str] = mapped_column(Text, nullable=False)
    json_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Rows per table.
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Who asked for it; none for the weekly one.
    built_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
