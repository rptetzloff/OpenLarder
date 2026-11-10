"""What local models suggest, and the embeddings they work from (SCOPING.md,
LLM-assisted data processing).

n8n writes both, through a role that reads only public data (the public_
views of migration 0029) and can write nothing else; an admin accepts or
dismisses each suggestion on the site, and accepting is an ordinary admin
edit. Like flags, these are moderation data, not catalog data: not in the
ODbL export.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openlarder.models.base import Base, uuid_pk

# EmbeddingGemma's size.
DIMENSIONS = 768


class IngredientEmbedding(Base):
    __tablename__ = "ingredient_embeddings"
    __table_args__ = (
        CheckConstraint("model <> ''", name="model_not_empty"),
        Index(
            "ix_ingredient_embeddings_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    # The name embedded: one that differs from the ingredient's now was
    # renamed since, and is embedded again.
    text_embedded: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSIONS), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Suggestion(Base):
    __tablename__ = "suggestions"
    __table_args__ = (
        CheckConstraint("kind IN ('merge', 'parent', 'line_fix', 'tag')", name="kind_known"),
        CheckConstraint("status IN ('open', 'accepted', 'dismissed')", name="status_known"),
        CheckConstraint("(status = 'open') = (decided_at IS NULL)", name="decided_when_closed"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint("model <> '' AND prompt_version <> ''", name="model_named"),
        # One open suggestion per kind and target, so a rerun inserts nothing
        # new (ON CONFLICT DO NOTHING); a dismissed one is found by the
        # workflow's NOT EXISTS and not suggested again.
        Index(
            "uq_suggestions_open",
            "kind",
            "target",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_suggestions_kind_status", "kind", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # merge or parent: two ingredient ids, the lower first; line_fix: a flag;
    # tag: a recipe's id and a tag's (0033).
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[object] = mapped_column(JSONB, nullable=False)
    proposal: Mapped[object] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    # Which model and prompt, so a bad batch can be found and reverted.
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
