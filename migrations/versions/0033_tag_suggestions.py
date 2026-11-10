"""Tag suggestions from a local model, and the public views it reads.

Workflow 4 (SCOPING.md, LLM-assisted data processing) suggests tags for
recipes from their title, chapter, source and ingredients, into the
Suggestions queue as kind 'tag'. It reads, like the others, only what
someone signed out sees: public_recipes, public_tags and public_recipe_tags
leave out private collections as public_ingredient_lines does. *Ray,
2026-11-09: tags by hand and by source first, then a local model.*

The n8n role is given the new views here when it exists, since the views'
owner may; scripts/n8n_role.sql grants them to a role made later.

Revision ID: 0033
Revises: 0032
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# As in 0029: what someone signed out can't see.
_HIDDEN_RECIPES = "SELECT r.id FROM recipes r JOIN sources s ON s.id = r.source_id WHERE s.private"

VIEWS = {
    "public_recipes": f"""
        SELECT r.id, r.title, r.chapter, s.id AS source_id, s.title AS source_title,
               s.kind::text AS source_kind
        FROM recipes r
        JOIN sources s ON s.id = r.source_id
        WHERE r.id NOT IN ({_HIDDEN_RECIPES})
    """,
    "public_tags": """
        SELECT t.id, t.kind::text AS kind, t.name FROM tags t
    """,
    # Each public recipe's tags, its own and its source's.
    "public_recipe_tags": f"""
        SELECT rt.recipe_id, rt.tag_id, false AS from_source
        FROM recipe_tags rt
        WHERE rt.recipe_id NOT IN ({_HIDDEN_RECIPES})
        UNION
        SELECT r.id, st.tag_id, true
        FROM source_tags st
        JOIN recipes r ON r.source_id = st.source_id
        WHERE r.id NOT IN ({_HIDDEN_RECIPES})
    """,
}

ROLE = "n8n_suggester"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_suggestions_kind_known"), "suggestions", type_="check")
    op.create_check_constraint(
        "kind_known", "suggestions", "kind IN ('merge', 'parent', 'line_fix', 'tag')"
    )
    for name, query in VIEWS.items():
        op.execute(f"CREATE VIEW {name} AS {query}")
    views = ", ".join(VIEWS)
    op.execute(
        f"""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                GRANT SELECT ON {views} TO {ROLE};
            END IF;
        END $$"""
    )


def downgrade() -> None:
    for name in reversed(list(VIEWS)):
        op.execute(f"DROP VIEW {name}")
    op.execute("DELETE FROM suggestions WHERE kind = 'tag'")
    op.drop_constraint(op.f("ck_suggestions_kind_known"), "suggestions", type_="check")
    op.create_check_constraint(
        "kind_known", "suggestions", "kind IN ('merge', 'parent', 'line_fix')"
    )
