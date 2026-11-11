"""Other names for ingredients from their Wikidata items, suggested beside
the links (wikidata_names.py): ingredient_link_suggestions takes source
'alias', with the name and its region.

Revision ID: 0057
Revises: 0056
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0057"
down_revision: str | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

T = "ingredient_link_suggestions"
UQ = "uq_ingredient_link_suggestions_record"
ONE = (
    "(source = 'fdc' AND fdc_id IS NOT NULL AND wikidata_id IS NULL)"
    " OR (source = 'wikidata' AND wikidata_id ~ '^Q[1-9][0-9]*$' AND fdc_id IS NULL"
    " AND alias IS NULL)"
    " OR (source = 'alias' AND wikidata_id ~ '^Q[1-9][0-9]*$' AND fdc_id IS NULL"
    " AND alias <> '')"
)
OLD_ONE = (
    "(source = 'fdc' AND fdc_id IS NOT NULL AND wikidata_id IS NULL)"
    " OR (source = 'wikidata' AND wikidata_id ~ '^Q[1-9][0-9]*$' AND fdc_id IS NULL)"
)


def upgrade() -> None:
    op.add_column(T, sa.Column("alias", sa.Text(), nullable=True))
    op.add_column(T, sa.Column("region", sa.Text(), nullable=True))
    op.drop_constraint(op.f(f"ck_{T}_source_known"), T, type_="check")
    op.create_check_constraint(
        op.f(f"ck_{T}_source_known"), T, "source IN ('fdc', 'wikidata', 'alias')"
    )
    op.create_check_constraint(op.f(f"ck_{T}_region_known"), T, "region IN ('UK', 'AU')")
    op.drop_constraint(op.f(f"ck_{T}_one_record"), T, type_="check")
    op.create_check_constraint(op.f(f"ck_{T}_one_record"), T, ONE)
    op.drop_constraint(UQ, T, type_="unique")
    op.create_unique_constraint(
        UQ,
        T,
        ["ingredient_id", "source", "fdc_id", "wikidata_id", "alias", "region"],
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {T} WHERE source = 'alias'")
    op.drop_constraint(UQ, T, type_="unique")
    op.create_unique_constraint(
        UQ,
        T,
        ["ingredient_id", "source", "fdc_id", "wikidata_id"],
        postgresql_nulls_not_distinct=True,
    )
    op.drop_constraint(op.f(f"ck_{T}_one_record"), T, type_="check")
    op.create_check_constraint(op.f(f"ck_{T}_one_record"), T, OLD_ONE)
    op.drop_constraint(op.f(f"ck_{T}_region_known"), T, type_="check")
    op.drop_constraint(op.f(f"ck_{T}_source_known"), T, type_="check")
    op.create_check_constraint(op.f(f"ck_{T}_source_known"), T, "source IN ('fdc', 'wikidata')")
    op.drop_column(T, "region")
    op.drop_column(T, "alias")
