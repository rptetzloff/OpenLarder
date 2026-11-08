"""A matching key on authors' names.

A typed or imported name is matched to an author by a key that ignores
case, accents, punctuation, bracketed notes and "Last, First" order
(author_names.name_key), among every author, Open Library's included: two
records of one person ("Katarina Cermelj" typed, Open Library's
"Cermelj, Katarina") were the result of leaving Open Library's out. *Ray,
2026-11-08.* Not unique: two cooks can share a name, and a name matching
several authors makes a new one, for merging by hand.

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from openlarder.author_names import name_key

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("authors", sa.Column("name_key", sa.Text()))
    bind = op.get_bind()
    for author_id, name in bind.execute(sa.text("SELECT id, name FROM authors")).all():
        bind.execute(
            sa.text("UPDATE authors SET name_key = :k WHERE id = :i"),
            {"k": name_key(name), "i": author_id},
        )
    op.alter_column("authors", "name_key", nullable=False)
    op.create_index(op.f("ix_authors_name_key"), "authors", ["name_key"])


def downgrade() -> None:
    op.drop_index(op.f("ix_authors_name_key"), "authors")
    op.drop_column("authors", "name_key")
