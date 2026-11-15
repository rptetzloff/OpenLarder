"""The last of the affiliate variables is copied onto its shop.

*Decided by Ray, 2026-11-13* (round 4, part D3): a release after the shops
moved to their table (0073), the eight environment variables their settings
were in stop being read. For that one release the app still took a setting
from its variable for a shop nobody had changed that had none of its own,
which covered a variable set after 0073 ran. This makes that standing: such
a shop gets the variable's value and is switched on, exactly what the app
was showing. So taking the variables out of the app changes no link,
whether or not anyone moved the setting by hand.

Where every variable set was already copied by 0073, which is the usual
case, this changes nothing.

Like 0073, it reads the environment itself, not the app's settings, which
no longer have these. A value of the wrong shape is left where it is: the
app refused to start with one, so there shouldn't be any. It writes no
edit history: this is the seeding finished, not somebody's change
(*Claude's choice, 2026-11-15*).

Revision ID: 0076
Revises: 0075
"""

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0076"
down_revision: str | None = "0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# kind, key, the column its setting is in, and the variable it was in.
VARIABLES = [
    ("bookseller", "bookshop", "affiliate_id", "BOOKSHOP_AFFILIATE_ID"),
    ("bookseller", "amazon", "affiliate_id", "AMAZON_TAG"),
    ("bookseller", "bn", "wrapper_template", "BARNES_NOBLE_LINK"),
    ("bookseller", "thriftbooks", "wrapper_template", "THRIFTBOOKS_LINK"),
    ("bookseller", "bookoutlet", "wrapper_template", "BOOKOUTLET_LINK"),
    ("bookseller", "kobo", "wrapper_template", "KOBO_LINK"),
    ("grocer", "instacart", "wrapper_template", "INSTACART_LINK"),
    ("grocer", "amazon", "affiliate_id", "AMAZON_TAG"),
    ("grocer", "walmart", "wrapper_template", "WALMART_LINK"),
]


def _well_formed(variable: str, value: str) -> bool:
    """What config.py asked of each, before it stopped having them."""
    if variable == "BOOKSHOP_AFFILIATE_ID":
        return value.isdigit()
    if variable == "AMAZON_TAG":
        return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}", value) is not None
    return value.startswith("https://") and "{url}" in value


def updates(environ) -> list[tuple[str, dict]]:
    """A statement for each variable that's set: its value onto its shop,
    switched on, if nobody has changed the shop and it has none."""
    found = []
    for kind, key, column, variable in VARIABLES:
        value = (environ.get(f"OPENLARDER_{variable}") or "").strip()
        if not value or not _well_formed(variable, value):
            continue
        found.append(
            (
                f"UPDATE shops SET {column} = :value, enabled = true"
                f" WHERE kind = :kind AND key = :key AND updated_by IS NULL AND {column} IS NULL",
                {"value": value, "kind": kind, "key": key},
            )
        )
    return found


def upgrade() -> None:
    todo = updates(os.environ)
    if not todo:
        return
    bind = op.get_bind()
    # Not an edit, so not in the edit history (0074's trigger).
    op.execute("ALTER TABLE shops DISABLE TRIGGER record_revision")
    for statement, values in todo:
        bind.execute(sa.text(statement), values)
    op.execute("ALTER TABLE shops ENABLE TRIGGER record_revision")


def downgrade() -> None:
    # Nothing to take back: which settings this copied isn't recorded, and
    # the release before reads a shop's own setting ahead of its variable.
    pass
