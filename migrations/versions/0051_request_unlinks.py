"""A request lets go of a book that stops being public.

Migration 0050 links a request to a public, published source. A source that
then goes back to waiting for review (a contributor's book is saved, then
marked pending, in one transaction), is sent back, or turns private, would
leave the request pointing at a book its readers can't see. So an open or
claimed request lets go of it; it links again if the book is published.

Revision ID: 0051
Revises: 0050
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION book_requests_unlink_source() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          UPDATE book_requests
             SET source_id = NULL
           WHERE source_id = NEW.id AND status IN ('open', 'claimed');
          RETURN NULL;
        END $$;

        CREATE TRIGGER sources_unlink_requests
          AFTER UPDATE OF review, private ON sources
          FOR EACH ROW WHEN (NEW.review <> 'published' OR NEW.private)
          EXECUTE FUNCTION book_requests_unlink_source();

        -- Any left linked to a book that isn't public now.
        UPDATE book_requests r
           SET source_id = NULL
          FROM sources s
         WHERE s.id = r.source_id
           AND r.status IN ('open', 'claimed')
           AND (s.review <> 'published' OR s.private);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER sources_unlink_requests ON sources;
        DROP FUNCTION book_requests_unlink_source();
        """
    )
