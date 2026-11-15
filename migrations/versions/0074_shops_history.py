"""A shop's changes are in the edit history.

Round 4, D2 (*decided by Ray, 2026-11-13*): an administrator changes the
shops from the site, and each change is recorded with who and when, as the
catalog's are. Until now nothing could change a row but migration 0073,
which seeded them, and seeds aren't edits: the trigger starts here, after
them.

Revision ID: 0074
Revises: 0073
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0074"
down_revision: str | None = "0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TRIGGER record_revision AFTER INSERT OR UPDATE OR DELETE ON shops"
        " FOR EACH ROW EXECUTE FUNCTION record_revision('none')"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER record_revision ON shops")
