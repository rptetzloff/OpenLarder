"""Review: what a contributor adds waits for a moderator, and everyone who
adds to the catalog accepts the contributor agreement first.

*Ray, 2026-11-10:* contributors add books and their recipes; each is hidden
from everyone but them and moderators until a moderator approves it, one
at a time or all of a book's at once; one sent back keeps the moderator's
reason, and the contributor fixes it and sends it again. Everyone who adds
accepts the agreement, the owner included.

The views n8n reads (0029, 0033) leave out what's waiting, as they leave
out private collections.

Revision ID: 0041
Revises: 0040
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATES = "review IN ('published', 'pending', 'returned')"


def _views(hidden: str) -> dict[str, str]:
    """0029's and 0033's views, with what someone signed out can't see."""
    public_ingredient_ids = f"""
        SELECT i.id FROM ingredients i
        WHERE NOT EXISTS (
            SELECT 1 FROM ingredient_options o
            WHERE o.ingredient_id = i.id AND o.recipe_id IN ({hidden})
        ) OR EXISTS (
            SELECT 1 FROM ingredient_options o
            WHERE o.ingredient_id = i.id AND o.recipe_id NOT IN ({hidden})
        )
    """
    return {
        "public_ingredients": f"""
            SELECT i.id, i.name, i.match_key,
                   CASE WHEN i.parent_id IN ({public_ingredient_ids}) THEN i.parent_id END
                       AS parent_id
            FROM ingredients i
            WHERE i.id IN ({public_ingredient_ids})
        """,
        "public_ingredient_aliases": f"""
            SELECT a.id, a.ingredient_id, a.name, a.region
            FROM ingredient_aliases a
            WHERE a.ingredient_id IN ({public_ingredient_ids})
        """,
        "public_ingredient_lines": f"""
            SELECT l.id, l.recipe_id, r.title AS recipe_title, s.id AS source_id,
                   s.title AS source_title, l.position, l.original_text
            FROM recipe_ingredients l
            JOIN recipes r ON r.id = l.recipe_id
            JOIN sources s ON s.id = r.source_id
            WHERE l.recipe_id NOT IN ({hidden})
        """,
        "public_open_flags": f"""
            SELECT f.id, f.recipe_id, f.kind, f.detail, f.created_at
            FROM recipe_flags f
            WHERE f.resolved_at IS NULL AND f.recipe_id NOT IN ({hidden})
        """,
        "public_recipes": f"""
            SELECT r.id, r.title, r.chapter, s.id AS source_id, s.title AS source_title,
                   s.kind::text AS source_kind
            FROM recipes r
            JOIN sources s ON s.id = r.source_id
            WHERE r.id NOT IN ({hidden})
        """,
        "public_recipe_tags": f"""
            SELECT rt.recipe_id, rt.tag_id, false AS from_source
            FROM recipe_tags rt
            WHERE rt.recipe_id NOT IN ({hidden})
            UNION
            SELECT r.id, st.tag_id, true
            FROM source_tags st
            JOIN recipes r ON r.source_id = st.source_id
            WHERE r.id NOT IN ({hidden})
        """,
    }


BEFORE = "SELECT r.id FROM recipes r JOIN sources s ON s.id = r.source_id WHERE s.private"
AFTER = (
    "SELECT r.id FROM recipes r JOIN sources s ON s.id = r.source_id"
    " WHERE s.private OR s.review <> 'published' OR r.review <> 'published'"
)


def _review_columns(table: str) -> None:
    op.add_column(table, sa.Column("review", sa.Text(), server_default="published", nullable=False))
    op.add_column(table, sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("reviewed_by", sa.UUID(), nullable=True))
    op.add_column(table, sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(op.f(f"ck_{table}_review_known"), table, STATES)
    op.create_foreign_key(
        op.f(f"fk_{table}_reviewed_by_users"),
        table,
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        f"ix_{table}_waiting",
        table,
        ["review"],
        postgresql_where=sa.text("review <> 'published'"),
    )


def upgrade() -> None:
    op.add_column("users", sa.Column("agreed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("agreed_version", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_users_agreement_whole"),
        "users",
        "(agreed_at IS NULL) = (agreed_version IS NULL)",
    )
    op.add_column("sources", sa.Column("created_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_sources_created_by_users"),
        "sources",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_sources_created_by"), "sources", ["created_by"])
    _review_columns("sources")
    _review_columns("recipes")
    # A family collection is its owner's, and isn't reviewed.
    op.create_check_constraint(
        op.f("ck_sources_family_not_reviewed"),
        "sources",
        "kind <> 'family' OR review = 'published'",
    )
    for name, query in _views(AFTER).items():
        op.execute(f"CREATE OR REPLACE VIEW {name} AS {query}")


def downgrade() -> None:
    for name, query in _views(BEFORE).items():
        op.execute(f"CREATE OR REPLACE VIEW {name} AS {query}")
    op.drop_constraint(op.f("ck_sources_family_not_reviewed"), "sources", type_="check")
    for table in ("recipes", "sources"):
        op.drop_index(f"ix_{table}_waiting", table_name=table)
        op.drop_constraint(op.f(f"fk_{table}_reviewed_by_users"), table, type_="foreignkey")
        op.drop_constraint(op.f(f"ck_{table}_review_known"), table, type_="check")
        for column in ("reviewed_at", "reviewed_by", "review_note", "review"):
            op.drop_column(table, column)
    op.drop_index(op.f("ix_sources_created_by"), table_name="sources")
    op.drop_constraint(op.f("fk_sources_created_by_users"), "sources", type_="foreignkey")
    op.drop_column("sources", "created_by")
    op.drop_constraint(op.f("ck_users_agreement_whole"), "users", type_="check")
    op.drop_column("users", "agreed_version")
    op.drop_column("users", "agreed_at")
