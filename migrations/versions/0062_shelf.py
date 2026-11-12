"""Your shelf: the books you own, and which edition, so search can keep to
them and a recipe's page can show your edition's page number.

*SCOPING.md, "Personal shelf: mark books you own, filter search to your
shelf"; TODO.md, beside the larder.* Private, as the larder is: not catalog
data, so not in the edit history, the dumps or the API's public reads. A
book merge moves it to the book kept; deleting the account deletes it.

Revision ID: 0062
Revises: 0061
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062"
down_revision: str | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shelf_books",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("edition_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_shelf_books_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_shelf_books_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            ["editions.id"],
            name=op.f("fk_shelf_books_edition_id_editions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("user_id", "source_id", name=op.f("pk_shelf_books")),
    )
    op.create_index(op.f("ix_shelf_books_source_id"), "shelf_books", ["source_id"])
    op.create_index(op.f("ix_shelf_books_edition_id"), "shelf_books", ["edition_id"])
    op.execute(
        "CREATE TRIGGER shelf_books_updated_at BEFORE UPDATE ON shelf_books "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.drop_table("shelf_books")
