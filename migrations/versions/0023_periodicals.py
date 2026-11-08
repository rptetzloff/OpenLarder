"""Magazines and newspapers as sources, and recipes in their issues.

Step 3 of sources beyond books (TODO.md). A magazine or newspaper is a
source; its parts are issues, named as the cover names them ("May 2024",
"Holiday 2023") or, for a newspaper, by date; a recipe is in an issue at a
page. *Ray, 2026-11-08.*

A recipe's location is now an edition, a web page or an issue, exactly one,
and a page goes with an edition or an issue.

Downgrade refuses while any magazine or newspaper exists, rather than drop
them.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_sources_kind_known"), "sources", type_="check")
    op.create_check_constraint(op.f("ck_sources_kind_known"), "sources", f"kind IN ({kinds})")


def upgrade() -> None:
    _kinds("'book', 'website', 'magazine', 'newspaper'")

    op.create_table(
        "issues",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("published_on", sa.Date()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_issues")),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_issues_source_id_sources"),
            ondelete="CASCADE",
        ),
        # The target of recipe_locations' composite key.
        sa.UniqueConstraint("source_id", "id", name=op.f("uq_issues_source_id_id")),
        sa.CheckConstraint("label <> ''", name=op.f("ck_issues_label_not_empty")),
    )
    op.create_index(
        "uq_issues_source_id_label", "issues", ["source_id", sa.text("lower(label)")], unique=True
    )
    op.execute(
        "CREATE TRIGGER issues_updated_at BEFORE UPDATE ON issues "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.add_column("recipe_locations", sa.Column("issue_id", UUID))
    op.create_foreign_key(
        op.f("fk_recipe_locations_source_id_issue_id_issues"),
        "recipe_locations",
        "issues",
        ["source_id", "issue_id"],
        ["source_id", "id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(op.f("ck_recipe_locations_one_place"), "recipe_locations", type_="check")
    op.create_check_constraint(
        op.f("ck_recipe_locations_one_place"),
        "recipe_locations",
        "num_nonnulls(edition_id, web_page_id, issue_id) = 1",
    )
    op.drop_constraint(
        op.f("ck_recipe_locations_page_needs_edition"), "recipe_locations", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_recipe_locations_page_needs_a_printing"),
        "recipe_locations",
        "page IS NULL OR edition_id IS NOT NULL OR issue_id IS NOT NULL",
    )
    op.create_unique_constraint(
        op.f("uq_recipe_locations_recipe_id_issue_id"),
        "recipe_locations",
        ["recipe_id", "issue_id"],
    )
    op.create_index(op.f("ix_recipe_locations_issue_id"), "recipe_locations", ["issue_id"])


def downgrade() -> None:
    held = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM sources WHERE kind IN ('magazine', 'newspaper')")
    )
    if held:
        raise RuntimeError(f"{held} magazines or newspapers exist; remove them before downgrading.")
    op.drop_index(op.f("ix_recipe_locations_issue_id"), "recipe_locations")
    op.drop_constraint(
        op.f("uq_recipe_locations_recipe_id_issue_id"), "recipe_locations", type_="unique"
    )
    op.drop_constraint(
        op.f("ck_recipe_locations_page_needs_a_printing"), "recipe_locations", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_recipe_locations_page_needs_edition"),
        "recipe_locations",
        "page IS NULL OR edition_id IS NOT NULL",
    )
    op.drop_constraint(op.f("ck_recipe_locations_one_place"), "recipe_locations", type_="check")
    op.create_check_constraint(
        op.f("ck_recipe_locations_one_place"),
        "recipe_locations",
        "num_nonnulls(edition_id, web_page_id) = 1",
    )
    op.drop_constraint(
        op.f("fk_recipe_locations_source_id_issue_id_issues"),
        "recipe_locations",
        type_="foreignkey",
    )
    op.drop_column("recipe_locations", "issue_id")
    op.drop_table("issues")
    _kinds("'book', 'website'")
