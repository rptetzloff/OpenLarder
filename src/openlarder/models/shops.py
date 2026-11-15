"""Where a link out of the site can earn: the booksellers on a book's page,
the grocers on an ingredient's, and (not yet) producers.

*Decided by Ray, 2026-11-13:* the affiliate settings move out of
environment variables, where changing one meant a redeploy, into a table an
administrator edits. Site configuration, not catalog: it's in no data dump.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, uuid_pk


class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint("kind IN ('bookseller', 'grocer', 'producer')", name="kind_known"),
        CheckConstraint(
            "builder IN ('bookshop', 'amazon', 'wrapped', 'template', 'direct')",
            name="builder_known",
        ),
        CheckConstraint("format IN ('print', 'ebook')", name="format_known"),
        CheckConstraint("earns IN ('affiliate', 'referral', 'none')", name="earns_known"),
        CheckConstraint("key ~ '^[a-z0-9-]+$'", name="key_shape"),
        CheckConstraint("label <> ''", name="label_not_empty"),
        # A key is unique among its kind, not among all: Amazon sells books
        # and Amazon Fresh groceries, both as "amazon", in /go/amazon/… and
        # /go/grocer/amazon/…, addresses already on the web.
        UniqueConstraint("kind", "key"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # In /go/ addresses, click records and people's saved choice of shops:
    # it never changes.
    key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # How the address a click goes to is made (shops.py).
    builder: Mapped[str] = mapped_column(Text, nullable=False)
    # An id or tag put into the shop's own address.
    affiliate_id: Mapped[str | None] = mapped_column(Text)
    # An affiliate network's deep link, with {url} where the shop's address goes.
    wrapper_template: Mapped[str | None] = mapped_column(Text)
    # The shop's address, with placeholders for the book or the ingredient.
    product_template: Mapped[str | None] = mapped_column(Text)
    # Booksellers only: what it sells the book as.
    format: Mapped[str | None] = mapped_column(Text)
    earns: Mapped[str] = mapped_column(Text, nullable=False, server_default="affiliate")
    # What's said beside its link.
    note: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # The order it's shown in, among its kind.
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Producers only.
    description: Mapped[str | None] = mapped_column(Text)
    offer: Mapped[str | None] = mapped_column(Text)
    # US state codes; None, everywhere.
    ships_to: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Who last changed it; None while it's as the migration seeded it.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
