"""Equipment: what a recipe can't be made without (migration 0079).
*Decided by Ray, 2026-11-15; his spec is in private/.*

A fact about a recipe, like an ingredient's name, so it is open data. It is
recorded the way ingredients are, with two differences:

- Some things are expected in any kitchen (a knife, a mixing bowl) and are
  never recorded on a recipe: `assumed`. They are in the list so that
  someone looking for "skillet" finds why no recipe names one.
- A thing can count as several others, where an ingredient counts as one:
  a multicooker counts as a pressure cooker and as a slow cooker (*Ray,
  2026-11-15*). So there is no parent column; equipment_counts_as holds
  each link.

A recipe's needs mirror its ingredient lines: recipe_equipment is one need,
in order, with a size where the source gives one ("9-inch"), and
equipment_options are what meets it, the source's first choice at rank 1
("stand mixer or hand mixer" is one need with two options).

Whether a recipe's needs have been recorded at all is
recipes.equipment_checked (models/catalog.py): a recipe nobody has looked
at is not one that needs nothing.

Rules the schema enforces: a name and a key mean one thing; nothing counts
as itself; an option belongs to its need's recipe, and names a thing once
in a need. Not enforced: loops in what counts as what (equipment.py
refuses them), or that nothing assumed is on a recipe.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, Timestamps, uuid_pk


def _fk(target: str, *, ondelete: str) -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=False)


class Equipment(Timestamps, Base):
    """One piece of equipment ("Stand mixer"), whatever a source calls it."""

    __tablename__ = "equipment"
    __table_args__ = (
        CheckConstraint("name <> ''", name="name_not_empty"),
        CheckConstraint("match_key <> ''", name="match_key_not_empty"),
        CheckConstraint("shopping_term <> ''", name="shopping_term_not_empty"),
        CheckConstraint("wikidata_id ~ '^Q[1-9][0-9]*$'", name="wikidata_id_format"),
        Index("uq_equipment_name", text("lower(name)"), unique=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # What a typed name is matched by, made as an ingredient's is
    # (ingredients.match_key): no case, plurals or punctuation.
    match_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Expected in any kitchen, so never recorded on a recipe.
    assumed: Mapped[bool] = mapped_column(nullable=False, server_default=false())
    # In the list: seeded, or added by a moderator, and so everyone's to
    # see. False for one a recipe's form brought in, which is seen only
    # with a recipe that needs it (visibility.equipment_seen_by; migration
    # 0081).
    listed: Mapped[bool] = mapped_column(nullable=False, server_default=true())
    # What to search for at a shop, when it differs from the name.
    shopping_term: Mapped[str | None] = mapped_column(Text)
    wikidata_id: Mapped[str | None] = mapped_column(Text)


class EquipmentAlias(Timestamps, Base):
    """Another name for a piece of equipment ("Stick blender")."""

    __tablename__ = "equipment_aliases"
    __table_args__ = (
        CheckConstraint("name <> ''", name="name_not_empty"),
        CheckConstraint("match_key <> ''", name="match_key_not_empty"),
        CheckConstraint("region IN ('US', 'UK', 'AU')", name="region_known"),
        # As ingredient_aliases: one meaning per name per region, an unmarked
        # one included, and one meaning per key among the unmarked, which
        # are the ones a typed name is matched by.
        Index(
            "uq_equipment_aliases_name_region",
            text("lower(name)"),
            "region",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "uq_equipment_aliases_match_key",
            "match_key",
            unique=True,
            postgresql_where=text("region IS NULL"),
        ),
        Index("ix_equipment_aliases_equipment_id", "equipment_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    equipment_id: Mapped[uuid.UUID] = _fk("equipment.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    match_key: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)


class EquipmentCountsAs(Base):
    """One thing counting as another: having a stand mixer covers a recipe
    that needs a mixer. Not the other way round."""

    __tablename__ = "equipment_counts_as"
    __table_args__ = (
        PrimaryKeyConstraint("equipment_id", "counts_as_id"),
        CheckConstraint("equipment_id <> counts_as_id", name="not_itself"),
        Index("ix_equipment_counts_as_counts_as_id", "counts_as_id"),
    )

    equipment_id: Mapped[uuid.UUID] = _fk("equipment.id", ondelete="CASCADE")
    # RESTRICT: a broader thing is merged away, not deleted out from under
    # what counts as it.
    counts_as_id: Mapped[uuid.UUID] = _fk("equipment.id", ondelete="RESTRICT")


class RecipeEquipment(Timestamps, Base):
    """One need of a recipe, in the order its source gives them."""

    __tablename__ = "recipe_equipment"
    __table_args__ = (
        UniqueConstraint("recipe_id", "position"),
        # The target of equipment_options' composite key.
        UniqueConstraint("recipe_id", "id"),
        CheckConstraint("detail <> ''", name="detail_not_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_id: Mapped[uuid.UUID] = _fk("recipes.id", ondelete="CASCADE")
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # A size or capacity ("9-inch", "6-quart"): never a method, a brand or
    # the source's words beyond the size.
    detail: Mapped[str | None] = mapped_column(Text)


class EquipmentOption(Timestamps, Base):
    """One thing that meets a need: rank 1 is the source's first choice."""

    __tablename__ = "equipment_options"
    __table_args__ = (
        # Carries the need's recipe_id, so an option can't be on one recipe
        # and its need on another. Named by hand: the convention's name runs
        # past Postgres' 63 characters.
        ForeignKeyConstraint(
            ["recipe_id", "recipe_equipment_id"],
            ["recipe_equipment.recipe_id", "recipe_equipment.id"],
            ondelete="CASCADE",
            name="fk_equipment_options_need",
        ),
        UniqueConstraint("recipe_equipment_id", "rank"),
        UniqueConstraint("recipe_equipment_id", "equipment_id"),
        CheckConstraint("rank >= 1", name="rank_positive"),
        # Counting the recipes that need a thing reads it in order, as
        # ingredient_options' does.
        Index("ix_equipment_options_equipment_id_recipe_id", "equipment_id", "recipe_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_equipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # RESTRICT: a thing a recipe needs is merged into another, not deleted.
    equipment_id: Mapped[uuid.UUID] = _fk("equipment.id", ondelete="RESTRICT")
