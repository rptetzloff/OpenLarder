"""Ratings (migration 0068; routers/ratings.py): each person's spoons for a
recipe. Shown only as an average and a count; not catalog data."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, PrimaryKeyConstraint, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, Timestamps


class RecipeRating(Timestamps, Base):
    __tablename__ = "recipe_ratings"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "recipe_id"),
        CheckConstraint("spoons BETWEEN 1 AND 5", name="spoons_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # One to five.
    spoons: Mapped[int] = mapped_column(SmallInteger, nullable=False)
