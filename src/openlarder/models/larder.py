"""The personal larder (migration 0046, routers/larder.py): each person's
lists of what they have. Private; not catalog data."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, Timestamps, uuid_pk


class LarderList(Timestamps, Base):
    __tablename__ = "larder_lists"
    __table_args__ = (CheckConstraint("name <> ''", name="name_not_empty"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Theirs to name: "Pantry", "Spice drawer", "Chest freezer".
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Their order.
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class LarderItem(Timestamps, Base):
    __tablename__ = "larder_items"
    __table_args__ = (
        CheckConstraint("name <> ''", name="name_not_empty"),
        CheckConstraint("state IN ('have', 'low', 'out')", name="state_known"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("larder_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Their own name for it ("Cholula Chipotle").
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # What it is (Chipotle Hot Sauce); none until matched. It counts as
    # everything above it too (hot sauce).
    ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="SET NULL"), index=True
    )
    # have, low (running low: still counts), or out (kept on the list, not
    # counted). No amounts.
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="have")
