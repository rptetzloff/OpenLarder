"""Requests follow their book into the catalog.

*Ray, 2026-11-09, step 2 of requests:* a request closes when anyone enters
its book, the book is linked to it as it's entered, and work on the book
keeps a claim alive. Done in the database, so every way in counts the same:
the forms, an import, a moderator approving a contributor's book.

When a public, published source has an edition with a request's ISBN (or,
for a request with no ISBN, the same title), the request is linked to it.
Once that source has a published recipe:

- an open request, or a claim gone quiet past 30 days, is done: the book is
  being indexed and nobody is queueing it;
- a live claim is kept alive instead (each recipe is work on it), and stays
  with its claimer until they mark it done.

A private family collection never links: it says nothing of itself.

Revision ID: 0050
Revises: 0049
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# routers/book_requests.py CLAIM_LAPSES.
LAPSES = "interval '30 days'"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE FUNCTION book_requests_follow(p_source uuid) RETURNS void
        LANGUAGE plpgsql AS $$
        BEGIN
          UPDATE book_requests r
             SET source_id = s.id,
                 active_at = CASE WHEN r.status = 'claimed' THEN now() ELSE r.active_at END
            FROM sources s
           WHERE s.id = p_source
             AND NOT s.private
             AND s.review = 'published'
             AND r.status IN ('open', 'claimed')
             AND r.source_id IS NULL
             AND (
               r.isbn13 IN (
                 SELECT e.isbn13 FROM editions e
                  WHERE e.source_id = s.id AND e.isbn13 IS NOT NULL
               )
               OR (r.isbn13 IS NULL AND lower(r.title) = lower(s.title))
             );

          IF EXISTS (
            SELECT 1 FROM recipes x
              JOIN sources s ON s.id = x.source_id
             WHERE x.source_id = p_source
               AND x.review = 'published'
               AND s.review = 'published'
               AND NOT s.private
          ) THEN
            UPDATE book_requests r
               SET status = CASE WHEN live THEN 'claimed' ELSE 'done' END,
                   claimed_by = CASE WHEN live THEN r.claimed_by END,
                   active_at = CASE WHEN live THEN now() ELSE r.active_at END,
                   closed_at = CASE WHEN live THEN NULL ELSE now() END
              FROM (
                SELECT q.id,
                       q.status = 'claimed' AND q.active_at >= now() - {LAPSES} AS live
                  FROM book_requests q
                 WHERE q.source_id = p_source AND q.status IN ('open', 'claimed')
              ) w
             WHERE r.id = w.id;
          END IF;
        END $$;

        -- An edition's or a recipe's source.
        CREATE FUNCTION book_requests_follow_row() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM book_requests_follow(NEW.source_id);
          RETURN NULL;
        END $$;

        CREATE FUNCTION book_requests_follow_source() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM book_requests_follow(NEW.id);
          RETURN NULL;
        END $$;

        CREATE TRIGGER editions_follow_requests
          AFTER INSERT OR UPDATE OF isbn13, source_id ON editions
          FOR EACH ROW WHEN (NEW.isbn13 IS NOT NULL)
          EXECUTE FUNCTION book_requests_follow_row();

        CREATE TRIGGER sources_follow_requests_insert
          AFTER INSERT ON sources
          FOR EACH ROW WHEN (NEW.review = 'published' AND NOT NEW.private)
          EXECUTE FUNCTION book_requests_follow_source();

        CREATE TRIGGER sources_follow_requests_update
          AFTER UPDATE OF review, private, title ON sources
          FOR EACH ROW WHEN (
            NEW.review = 'published' AND NOT NEW.private
            AND (OLD.review, OLD.private, OLD.title) IS DISTINCT FROM
                (NEW.review, NEW.private, NEW.title)
          )
          EXECUTE FUNCTION book_requests_follow_source();

        CREATE TRIGGER recipes_follow_requests_insert
          AFTER INSERT ON recipes
          FOR EACH ROW WHEN (NEW.review = 'published')
          EXECUTE FUNCTION book_requests_follow_row();

        CREATE TRIGGER recipes_follow_requests_update
          AFTER UPDATE OF review, source_id ON recipes
          FOR EACH ROW WHEN (
            NEW.review = 'published'
            AND (OLD.review, OLD.source_id) IS DISTINCT FROM (NEW.review, NEW.source_id)
          )
          EXECUTE FUNCTION book_requests_follow_row();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER recipes_follow_requests_update ON recipes;
        DROP TRIGGER recipes_follow_requests_insert ON recipes;
        DROP TRIGGER sources_follow_requests_update ON sources;
        DROP TRIGGER sources_follow_requests_insert ON sources;
        DROP TRIGGER editions_follow_requests ON editions;
        DROP FUNCTION book_requests_follow_source();
        DROP FUNCTION book_requests_follow_row();
        DROP FUNCTION book_requests_follow(uuid);
        """
    )
