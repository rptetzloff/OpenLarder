"""A removed row's revision keeps all of it, for revert to put it back.

0040's trigger leaves out what the database keeps for itself (match keys,
checked-at stamps) from every revision. A removal now keeps those too, all
but updated_at, so undoing it (history.revert) can insert the row whole:
ingredients' and aliases' match keys and authors' name keys are required.
Removals recorded before this can't be undone.

Revision ID: 0042
Revises: 0041
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _0040_function() -> str:
    spec = importlib.util.spec_from_file_location(
        "revisions_0040", Path(__file__).with_name("0040_revisions.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FUNCTION.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


OLD_NOISE = """  noise text[] := ARRAY['created_at', 'updated_at', 'match_key', 'name_key',
                        'wikidata_checked_at', 'archive_tried_at'];"""
NEW_NOISE = """  noise text[] := CASE WHEN TG_OP = 'DELETE' THEN ARRAY['updated_at']
                   ELSE ARRAY['created_at', 'updated_at', 'match_key', 'name_key',
                              'wikidata_checked_at', 'archive_tried_at'] END;"""


def upgrade() -> None:
    old = _0040_function()
    assert OLD_NOISE in old, "0040's trigger has changed"
    op.execute(old.replace(OLD_NOISE, NEW_NOISE))


def downgrade() -> None:
    op.execute(_0040_function())
