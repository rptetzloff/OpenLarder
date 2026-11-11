"""USDA FoodData Central's generic foods, kept here to link ingredients to
(fdc.py). Public domain (CC0), loaded from its bulk download: Foundation
Foods, SR Legacy and the survey foods (FNDDS); branded products and lab
samples are left out. *SCOPING.md, Ingredient normalization: FoodData
Central the base, Wikidata the backup (Ray, 2026-11-06); names stay the
household index's (2026-11-07).*"""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base

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
