"""Authors and credits: works credit authors in order, by role.

Replaces works.authors, a plain list of names. Each distinct name becomes one
author, so two books printing the identical name share an author; telling
apart two people with one name, or joining one person printed two ways, is a
merge for review. Each name becomes an 'author' credit in its printed order,
and keeps the printed name. A name repeated within one book is credited once.

Downgrade refuses while anything exists that a list of names can't hold --
a role other than author, a link, an Open Library or Wikidata id, or an
organisation -- rather than drop it silently.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
TABLES = ("authors", "author_links", "work_credits")


def _id() -> sa.Column:
    return sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "authors",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), server_default="person", nullable=False),
        sa.Column("open_library_author_id", sa.Text()),
        sa.Column("wikidata_id", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_authors"),
        sa.UniqueConstraint("open_library_author_id", name="uq_authors_open_library_author_id"),
        sa.UniqueConstraint("wikidata_id", name="uq_authors_wikidata_id"),
        sa.CheckConstraint("name <> ''", name="ck_authors_name_not_empty"),
        sa.CheckConstraint("kind IN ('person', 'organisation')", name="ck_authors_kind_known"),
        sa.CheckConstraint("wikidata_id ~ '^Q[1-9][0-9]*$'", name="ck_authors_wikidata_id_format"),
    )
    op.create_index(
        "ix_authors_name_trgm",
        "authors",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "author_links",
        _id(),
        sa.Column("author_id", UUID, nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("label", sa.Text()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_author_links"),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["authors.id"],
            ondelete="CASCADE",
            name="fk_author_links_author_id_authors",
        ),
        sa.UniqueConstraint("author_id", "url", name="uq_author_links_author_id_url"),
        sa.CheckConstraint("url <> ''", name="ck_author_links_url_not_empty"),
    )

    op.create_table(
        "work_credits",
        _id(),
        sa.Column("work_id", UUID, nullable=False),
        sa.Column("author_id", UUID, nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("role", sa.Text(), server_default="author", nullable=False),
        sa.Column("credited_as", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_work_credits"),
        sa.ForeignKeyConstraint(
            ["work_id"], ["works.id"], ondelete="CASCADE", name="fk_work_credits_work_id_works"
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["authors.id"],
            ondelete="RESTRICT",
            name="fk_work_credits_author_id_authors",
        ),
        sa.UniqueConstraint("work_id", "position", name="uq_work_credits_work_id_position"),
        sa.UniqueConstraint(
            "work_id", "author_id", "role", name="uq_work_credits_work_id_author_id_role"
        ),
        sa.CheckConstraint("credited_as <> ''", name="ck_work_credits_credited_as_not_empty"),
        sa.CheckConstraint(
            "role IN ('author', 'editor', 'contributor', 'photographer', 'illustrator',"
            " 'translator')",
            name="ck_work_credits_role_known",
        ),
    )
    op.create_index("ix_work_credits_author_id", "work_credits", ["author_id"])

    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )

    op.execute(
        """
        INSERT INTO authors (name)
        SELECT DISTINCT name FROM works, unnest(authors) AS name WHERE name <> ''
        """
    )
    op.execute(
        """
        INSERT INTO work_credits (work_id, author_id, position, role, credited_as)
        SELECT DISTINCT ON (w.id, n.name) w.id, a.id, n.ord::smallint, 'author', n.name
        FROM works w
        CROSS JOIN LATERAL unnest(w.authors) WITH ORDINALITY AS n(name, ord)
        JOIN authors a ON a.name = n.name
        ORDER BY w.id, n.name, n.ord
        """
    )
    op.drop_column("works", "authors")


def downgrade() -> None:
    kept = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM work_credits WHERE role <> 'author')"
                " + (SELECT count(*) FROM author_links)"
                " + (SELECT count(*) FROM authors WHERE open_library_author_id IS NOT NULL"
                "    OR wikidata_id IS NOT NULL OR kind <> 'person')"
            )
        )
        .scalar_one()
    )
    if kept:
        raise RuntimeError(
            f"{kept} row(s) hold a role, link, external id or organisation that a list of"
            " author names cannot store. Remove them first if losing them is intended."
        )

    op.add_column(
        "works",
        sa.Column("authors", pg.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    )
    op.execute(
        """
        UPDATE works w
        SET authors = c.names
        FROM (
            SELECT work_id, array_agg(credited_as ORDER BY position) AS names
            FROM work_credits GROUP BY work_id
        ) c
        WHERE c.work_id = w.id
        """
    )
    for table in reversed(TABLES):
        op.drop_table(table)
