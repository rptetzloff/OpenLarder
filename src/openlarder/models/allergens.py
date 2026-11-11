"""Allergens on ingredients (allergens.py, migration 0059)."""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, Timestamps, uuid_pk

STATUSES = ("contains", "may_contain", "free")


class Allergen(Base):
    """One of the allergens the catalog records: the US's nine major
    allergens and the EU's fourteen together."""

    __tablename__ = "allergens"
    __table_args__ = (
        CheckConstraint("key ~ '^[a-z_]+$'", name="key_format"),
        CheckConstraint("label <> ''", name="label_not_empty"),
    )

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class IngredientAllergen(Timestamps, Base):
    """What an ingredient records about one allergen: it contains it, may
    contain it, or doesn't, which overrides what a broader ingredient
    records. Narrower ingredients inherit it (allergens.recorded)."""

    __tablename__ = "ingredient_allergens"
    __table_args__ = (
        CheckConstraint("status IN ('contains', 'may_contain', 'free')", name="status_known"),
        UniqueConstraint("ingredient_id", "allergen"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    allergen: Mapped[str] = mapped_column(
        Text, ForeignKey("allergens.key", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)


class DietAllergen(Base):
    """An allergen a diet avoids (Dairy-Free: milk), for a recipe's page to
    check its lines against (diets.py)."""

    __tablename__ = "diet_allergens"
    __table_args__ = (PrimaryKeyConstraint("diet_tag_id", "allergen"),)

    diet_tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE")
    )
    allergen: Mapped[str] = mapped_column(
        Text, ForeignKey("allergens.key", ondelete="CASCADE"), index=True
    )
