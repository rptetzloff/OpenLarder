"""Suggested links from ingredients to FoodData Central and Wikidata
(fdc_match.py), for a moderator to accept or dismiss.

Revision ID: 0056
Revises: 0055
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingredient_link_suggestions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("ingredient_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("fdc_id", sa.Integer(), nullable=True),
        sa.Column("wikidata_id", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("certainty", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('fdc', 'wikidata')",
            name=op.f("ck_ingredient_link_suggestions_source_known"),
        ),
        sa.CheckConstraint(
            "certainty IN ('likely', 'unsure')",
            name=op.f("ck_ingredient_link_suggestions_certainty_known"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'accepted', 'dismissed')",
            name=op.f("ck_ingredient_link_suggestions_status_known"),
        ),
        sa.CheckConstraint(
            "(status = 'open') = (decided_at IS NULL)",
            name=op.f("ck_ingredient_link_suggestions_decided_when_closed"),
        ),
        sa.CheckConstraint(
            "(source = 'fdc' AND fdc_id IS NOT NULL AND wikidata_id IS NULL)"
            " OR (source = 'wikidata' AND wikidata_id ~ '^Q[1-9][0-9]*$' AND fdc_id IS NULL)",
            name=op.f("ck_ingredient_link_suggestions_one_record"),
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_ingredient_link_suggestions_ingredient_id_ingredients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fdc_id"],
            ["fdc_foods.fdc_id"],
            name=op.f("fk_ingredient_link_suggestions_fdc_id_fdc_foods"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_ingredient_link_suggestions_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingredient_link_suggestions")),
        sa.UniqueConstraint(
            "ingredient_id",
            "source",
            "fdc_id",
            "wikidata_id",
            name="uq_ingredient_link_suggestions_record",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_ingredient_link_suggestions_open",
        "ingredient_link_suggestions",
        ["source"],
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_table("ingredient_link_suggestions")
