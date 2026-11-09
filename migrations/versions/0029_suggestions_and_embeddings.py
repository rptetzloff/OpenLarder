"""Suggestions from local models, the ingredient embeddings they work from,
and the public-only views their database role reads (SCOPING.md,
LLM-assisted data processing).

Needs pgvector. CREATE EXTENSION needs a superuser unless the extension is
already there, so on a database whose app role isn't one, a superuser runs
it first; IF NOT EXISTS then makes this a no-op. The downgrade leaves the
extension, for the same reason.

The views are what visibility.py lets someone signed out see: nothing from a
private family collection, and no ingredient only one uses. A suggestion is
shown to admins, who can't see a private collection either, so a model must
never be shown one. scripts/n8n_role.sql grants the views, and not the
tables, to the role n8n uses.

Revision ID: 0029
Revises: 0028
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors visibility.py for a viewer who isn't signed in.
_HIDDEN_RECIPES = "SELECT r.id FROM recipes r JOIN sources s ON s.id = r.source_id WHERE s.private"
_PUBLIC_INGREDIENT_IDS = f"""
    SELECT i.id FROM ingredients i
    WHERE NOT EXISTS (
        SELECT 1 FROM ingredient_options o
        WHERE o.ingredient_id = i.id AND o.recipe_id IN ({_HIDDEN_RECIPES})
    ) OR EXISTS (
        SELECT 1 FROM ingredient_options o
        WHERE o.ingredient_id = i.id AND o.recipe_id NOT IN ({_HIDDEN_RECIPES})
    )
"""

VIEWS = {
    # A parent that isn't public reads as none.
    "public_ingredients": f"""
        SELECT i.id, i.name, i.match_key,
               CASE WHEN i.parent_id IN ({_PUBLIC_INGREDIENT_IDS}) THEN i.parent_id END
                   AS parent_id
        FROM ingredients i
        WHERE i.id IN ({_PUBLIC_INGREDIENT_IDS})
    """,
    "public_ingredient_aliases": f"""
        SELECT a.id, a.ingredient_id, a.name, a.region
        FROM ingredient_aliases a
        WHERE a.ingredient_id IN ({_PUBLIC_INGREDIENT_IDS})
    """,
    # Each public recipe's lines, with the recipe and source for context.
    "public_ingredient_lines": f"""
        SELECT l.id, l.recipe_id, r.title AS recipe_title, s.id AS source_id,
               s.title AS source_title, l.position, l.original_text
        FROM recipe_ingredients l
        JOIN recipes r ON r.id = l.recipe_id
        JOIN sources s ON s.id = r.source_id
        WHERE l.recipe_id NOT IN ({_HIDDEN_RECIPES})
    """,
    "public_open_flags": f"""
        SELECT f.id, f.recipe_id, f.kind, f.detail, f.created_at
        FROM recipe_flags f
        WHERE f.resolved_at IS NULL AND f.recipe_id NOT IN ({_HIDDEN_RECIPES})
    """,
}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "ingredient_embeddings",
        sa.Column("ingredient_id", sa.UUID(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("text_embedded", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("model <> ''", name=op.f("ck_ingredient_embeddings_model_not_empty")),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_ingredient_embeddings_ingredient_id_ingredients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ingredient_id", name=op.f("pk_ingredient_embeddings")),
    )
    op.create_index(
        "ix_ingredient_embeddings_embedding",
        "ingredient_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "suggestions",
        sa.Column("id", sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("target", postgresql.JSONB(), nullable=False),
        sa.Column("proposal", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("confidence", sa.Float()),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("decided_by", sa.UUID()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "kind IN ('merge', 'parent', 'line_fix')", name=op.f("ck_suggestions_kind_known")
        ),
        sa.CheckConstraint(
            "status IN ('open', 'accepted', 'dismissed')", name=op.f("ck_suggestions_status_known")
        ),
        sa.CheckConstraint(
            "(status = 'open') = (decided_at IS NULL)",
            name=op.f("ck_suggestions_decided_when_closed"),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name=op.f("ck_suggestions_confidence_range")
        ),
        sa.CheckConstraint(
            "model <> '' AND prompt_version <> ''", name=op.f("ck_suggestions_model_named")
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_suggestions_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suggestions")),
    )
    op.create_index(
        "uq_suggestions_open",
        "suggestions",
        ["kind", "target"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index("ix_suggestions_kind_status", "suggestions", ["kind", "status"])
    for name, query in VIEWS.items():
        op.execute(f"CREATE VIEW {name} AS {query}")


def downgrade() -> None:
    for name in VIEWS:
        op.execute(f"DROP VIEW {name}")
    op.drop_table("suggestions")
    op.drop_table("ingredient_embeddings")
