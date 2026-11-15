"""Sign-ups that followed a click on one of OpenLarder's own ads
(adclicks.py). *Decided by Ray, 2026-11-13.*

There is deliberately no user column, and nothing else an account could be
found by: no email, address or page. A row says that this ad click led to a
sign-up, and when. It's in no data dump and has no edit history.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, uuid_pk


class AdConversion(Base):
    __tablename__ = "ad_conversions"
    __table_args__ = (
        CheckConstraint("kind IN ('sign_up')", name="kind_known"),
        CheckConstraint(
            "click_id_type IN ('gclid', 'gbraid', 'wbraid')", name="click_id_type_known"
        ),
        # One click, one sign-up: a second account made from the same click
        # adds nothing.
        UniqueConstraint("kind", "click_id"),
        # What the export hasn't taken yet (scripts/ads_export.sql).
        Index(
            "ix_ad_conversions_pending",
            "converted_at",
            postgresql_where=text("exported_at IS NULL"),
        ),
    )

    # Sent to Google as the order id, which is how it ignores a row it has
    # read before.
    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    # As Google wrote it: click ids are case sensitive.
    click_id: Mapped[str] = mapped_column(Text, nullable=False)
    click_id_type: Mapped[str] = mapped_column(Text, nullable=False)
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    converted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # When the export copied it to the sheet; None until then.
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
