"""Flags: something about a recipe that needs a person to look at it.

Moderation data, not catalog data: not in the ODbL export. A flag is raised
when an entry or import looks wrong in a way the rules can't settle alone,
and stays until someone fixes the recipe or dismisses the flag. Admins see
every open flag; each person sees the flags on recipes they added.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, uuid_pk


class FlagKind(enum.StrEnum):
    # Another recipe in the same book has this title, on a different page.
    DUPLICATE_TITLE = "duplicate_title"
    NO_INGREDIENTS = "no_ingredients"
    NO_PAGE = "no_page"
    # A line broke an entry rule (an amount, too long) and was left out.
    LINE_REMOVED = "line_removed"
    # A line that looks like the tail of something split apart ("269)").
    LINE_FRAGMENT = "line_fragment"


class Resolution(enum.StrEnum):
    FIXED = "fixed"
    DISMISSED = "dismissed"


_KINDS = ", ".join(f"'{k.value}'" for k in FlagKind)


class RecipeFlag(Base):
    __tablename__ = "recipe_flags"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_KINDS})", name="kind_known"),
        CheckConstraint("resolution IN ('fixed', 'dismissed')", name="resolution_known"),
        CheckConstraint("(resolved_at IS NULL) = (resolution IS NULL)", name="resolved_together"),
        CheckConstraint("note <> ''", name="note_not_empty"),
        Index("ix_recipe_flags_recipe_id", "recipe_id"),
        Index("ix_recipe_flags_open", "created_at", postgresql_where=text("resolved_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    # What exactly: the removed line, the other recipe's page.
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolution: Mapped[str | None] = mapped_column(Text)
    # Why it was dismissed, or what was fixed.
    note: Mapped[str | None] = mapped_column(Text)
