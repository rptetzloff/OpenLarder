"""USDA FoodData Central's generic foods, kept here to link ingredients to
(fdc.py). Public domain (CC0), loaded from its bulk download: Foundation
Foods, SR Legacy and the survey foods (FNDDS); branded products and lab
samples are left out. *SCOPING.md, Ingredient normalization: FoodData
Central the base, Wikidata the backup (Ray, 2026-11-06); names stay the
household index's (2026-11-07).*"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, uuid_pk

DATA_TYPES = ("foundation_food", "sr_legacy_food", "survey_fndds_food")


class FdcFood(Base):
    __tablename__ = "fdc_foods"
    __table_args__ = (
        CheckConstraint("description <> ''", name="description_not_empty"),
        CheckConstraint(
            "data_type IN ('foundation_food', 'sr_legacy_food', 'survey_fndds_food')",
            name="data_type_known",
        ),
        Index(
            "ix_fdc_foods_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
    )

    # FoodData Central's own ID: fdc.nal.usda.gov/food-details/<id>.
    fdc_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    data_type: Mapped[str] = mapped_column(Text, nullable=False)
    # As FDC writes it: "Onions, raw".
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    # SR Legacy's NDB number, which Wikidata items cite (P1978).
    ndb_number: Mapped[int | None] = mapped_column(Integer, index=True)
    published: Mapped[date | None] = mapped_column(Date)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LinkSuggestion(Base):
    """A food or Wikidata item an ingredient is probably the same as, found
    by fdc_match.py, for a moderator to accept or dismiss (Admin ›
    Ingredient links). A dismissed one isn't suggested again."""

    __tablename__ = "ingredient_link_suggestions"
    __table_args__ = (
        CheckConstraint("source IN ('fdc', 'wikidata')", name="source_known"),
        CheckConstraint("certainty IN ('likely', 'unsure')", name="certainty_known"),
        CheckConstraint("status IN ('open', 'accepted', 'dismissed')", name="status_known"),
        CheckConstraint("(status = 'open') = (decided_at IS NULL)", name="decided_when_closed"),
        CheckConstraint(
            "(source = 'fdc' AND fdc_id IS NOT NULL AND wikidata_id IS NULL)"
            " OR (source = 'wikidata' AND wikidata_id ~ '^Q[1-9][0-9]*$' AND fdc_id IS NULL)",
            name="one_record",
        ),
        # NULLS NOT DISTINCT: each row has one of the two empty.
        UniqueConstraint(
            "ingredient_id",
            "source",
            "fdc_id",
            "wikidata_id",
            # The convention's name is past Postgres's 63 characters.
            name="uq_ingredient_link_suggestions_record",
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "ix_ingredient_link_suggestions_open",
            "source",
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    fdc_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("fdc_foods.fdc_id", ondelete="CASCADE")
    )
    wikidata_id: Mapped[str | None] = mapped_column(Text)
    # Wikidata's English label, as found.
    label: Mapped[str | None] = mapped_column(Text)
    # likely: the food's words are the name's; unsure: one word more, or
    # found through Wikidata's NDB numbers, which are often the plant.
    certainty: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
