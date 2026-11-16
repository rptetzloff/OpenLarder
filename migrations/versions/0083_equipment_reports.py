"""Reports about equipment: a reason on a recipe, and a kind of record.

*Ray's equipment spec, 2026-11-15:* "add a flag reason, 'Equipment is wrong
or missing'". A reason is what a person picks under "Report a problem", so
it is added there, as `equipment`: only a recipe has equipment recorded, so
only a recipe's report may give it, and the database refuses it on anything
else.

*Ray, 2026-11-16:* equipment is treated as ingredients are. An ingredient's
page has "Report a problem"; a piece of equipment's page gets it, so
`equipment` is a kind of record a report can be about.

Downgrade refuses while a report of either sort exists, rather than drop it.

Revision ID: 0083
Revises: 0082
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0083"
down_revision: str | None = "0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = "'recipe', 'source', 'ingredient', 'author'"
OLD_REASONS = "'wrong', 'duplicate', 'copied', 'spam', 'other'"


def _known(kinds: str, reasons: str) -> None:
    op.drop_constraint(op.f("ck_reports_target_kind_known"), "reports", type_="check")
    op.create_check_constraint(
        op.f("ck_reports_target_kind_known"), "reports", f"target_kind IN ({kinds})"
    )
    op.drop_constraint(op.f("ck_reports_reason_known"), "reports", type_="check")
    op.create_check_constraint(op.f("ck_reports_reason_known"), "reports", f"reason IN ({reasons})")


def upgrade() -> None:
    _known(OLD_KINDS + ", 'equipment'", OLD_REASONS + ", 'equipment'")
    op.create_check_constraint(
        op.f("ck_reports_equipment_reason_on_recipe"),
        "reports",
        "reason <> 'equipment' OR target_kind = 'recipe'",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        text("SELECT count(*) FROM reports WHERE reason = 'equipment' OR target_kind = 'equipment'")
    ):
        raise RuntimeError("Reports about equipment exist; deal with them before downgrading.")
    op.drop_constraint(op.f("ck_reports_equipment_reason_on_recipe"), "reports", type_="check")
    _known(OLD_KINDS, OLD_REASONS)
