"""Equipment's changes are in the edit history, and a merged thing's
address says where it went.

*Ray's equipment spec, 2026-11-15:* every change to equipment, its other
names and a recipe's needs is in the edit history and can be reverted, and
merging two things works as merging two ingredients does.

Until now nothing could change these rows but migration 0079, which seeded
them, and seeds aren't edits: the triggers start here, with the
moderators' tools (routers/equipment.py), as a shop's did in 0074.

- equipment, its other names and what counts as what are recorded as
  ingredients and their names are: not of any source. Another name, and a
  link saying what a thing counts as, hang off their thing, so its page's
  History has them.
- A recipe's needs and what meets each are recorded with their recipe, as
  its ingredient lines are, though nothing writes one yet.
- merged_records takes a third kind, "equipment": the id that went and the
  one kept (pages.py).

Revision ID: 0080
Revises: 0079
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0080"
down_revision: str | None = "0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Table, and how its source is found (0040): "none" for what isn't in a
# source, "recipe" for what hangs off one.
TRACKED = {
    "equipment": "none",
    "equipment_aliases": "none",
    "equipment_counts_as": "none",
    "recipe_equipment": "recipe",
    "equipment_options": "recipe",
}

# The trigger's last parent before this (0059), and the same with
# equipment's after it.
ALLERGEN_PARENT = "WHEN 'ingredient_allergens' THEN (row_ ->> 'ingredient_id')::uuid"
WITH_EQUIPMENT = (
    ALLERGEN_PARENT
    + "\n    WHEN 'equipment_aliases' THEN (row_ ->> 'equipment_id')::uuid"
    + "\n    WHEN 'equipment_counts_as' THEN (row_ ->> 'equipment_id')::uuid"
    + "\n    WHEN 'equipment_options' THEN (row_ ->> 'equipment_id')::uuid"
)


def _swap_parent(old: str, new: str) -> None:
    op.execute(
        f"""
        DO $do$
        DECLARE
          body text := pg_get_functiondef('record_revision'::regproc);
          changed text := replace(body, $a${old}$a$, $b${new}$b$);
        BEGIN
          IF changed = body THEN
            RAISE EXCEPTION 'record_revision is not as migration 0059 left it';
          END IF;
          EXECUTE changed;
        END
        $do$;
        """
    )


def upgrade() -> None:
    _swap_parent(ALLERGEN_PARENT, WITH_EQUIPMENT)
    for table, how in TRACKED.items():
        op.execute(
            f"CREATE TRIGGER record_revision AFTER INSERT OR UPDATE OR DELETE ON {table}"
            f" FOR EACH ROW EXECUTE FUNCTION record_revision('{how}')"
        )
    op.drop_constraint(op.f("ck_merged_records_kind_known"), "merged_records", type_="check")
    op.create_check_constraint(
        op.f("ck_merged_records_kind_known"),
        "merged_records",
        "kind IN ('ingredient', 'author', 'equipment')",
    )


def downgrade() -> None:
    # A merged thing's record can't stay under a kind the table won't have.
    op.execute("DELETE FROM merged_records WHERE kind = 'equipment'")
    op.drop_constraint(op.f("ck_merged_records_kind_known"), "merged_records", type_="check")
    op.create_check_constraint(
        op.f("ck_merged_records_kind_known"), "merged_records", "kind IN ('ingredient', 'author')"
    )
    for table in TRACKED:
        op.execute(f"DROP TRIGGER record_revision ON {table}")
    _swap_parent(WITH_EQUIPMENT, ALLERGEN_PARENT)
