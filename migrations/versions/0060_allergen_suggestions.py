"""Allergen suggestions, and the public views n8n reads them from.

The Suggestions queue takes kind 'allergen': an ingredient, an allergen,
and contains or may_contain (allergen_rules.py, and n8n's Workflow 5).
public_allergens and public_ingredient_allergens show what public
ingredients record, so a workflow skips them, as the other public_ views
leave out what only private collections use.

Revision ID: 0060
Revises: 0059
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0060"
down_revision: str | None = "0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEWS = {
    "public_allergens": "SELECT a.key, a.label, a.position FROM allergens a",
    "public_ingredient_allergens": """
        SELECT ia.ingredient_id, ia.allergen, ia.status
        FROM ingredient_allergens ia
        WHERE ia.ingredient_id IN (SELECT id FROM public_ingredients)
    """,
}

ROLE = "n8n_suggester"
BEFORE = "kind IN ('merge', 'parent', 'line_fix', 'tag')"
AFTER = "kind IN ('merge', 'parent', 'line_fix', 'tag', 'allergen')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_suggestions_kind_known"), "suggestions", type_="check")
    op.create_check_constraint("kind_known", "suggestions", AFTER)
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
    op.execute("DELETE FROM suggestions WHERE kind = 'allergen'")
    op.drop_constraint(op.f("ck_suggestions_kind_known"), "suggestions", type_="check")
    op.create_check_constraint("kind_known", "suggestions", BEFORE)
