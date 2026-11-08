"""A matching key on ingredient aliases.

Merging one ingredient into another keeps the merged name as an alias, and
renaming keeps the old name, so lines written that way go on matching the
ingredient they were moved to. Lines are matched by key (migration 0015),
so aliases need one too, made by the same function. Only unmarked aliases
match lines, since a book's region isn't known, and one of them per key, so
a key means one ingredient; "spring onion" can still mean one thing in the
UK and another in Australia. That no alias shares a key with an ingredient
is kept by ingredients.py, which makes both.

Existing aliases are keyed now. Upgrade refuses if two unmarked ones share
a key, rather than choose which to keep.

Revision ID: 0016
Revises: 0015
"""

from collections import Counter
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from openlarder.ingredients import match_key

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingredient_aliases", sa.Column("match_key", sa.Text()))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, name, region FROM ingredient_aliases")).all()
    keys = {i: match_key(n) for i, n, _ in rows}
    unmarked = Counter(keys[i] for i, _, region in rows if region is None)
    shared = [k for k, n in unmarked.items() if n > 1]
    if shared:
        raise RuntimeError(f"Ingredient aliases share a match key: {shared[:5]}")
    for alias_id, key in keys.items():
        bind.execute(
            sa.text("UPDATE ingredient_aliases SET match_key = :k WHERE id = :i"),
            {"k": key, "i": alias_id},
        )
    op.alter_column("ingredient_aliases", "match_key", nullable=False)
    op.create_check_constraint(
        op.f("ck_ingredient_aliases_match_key_not_empty"), "ingredient_aliases", "match_key <> ''"
    )
    op.create_index(
        "uq_ingredient_aliases_match_key",
        "ingredient_aliases",
        ["match_key"],
        unique=True,
        postgresql_where=sa.text("region IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_ingredient_aliases_match_key", "ingredient_aliases")
    op.drop_constraint(
        op.f("ck_ingredient_aliases_match_key_not_empty"), "ingredient_aliases", type_="check"
    )
    op.drop_column("ingredient_aliases", "match_key")
