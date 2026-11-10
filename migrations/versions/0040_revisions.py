"""Edit history: every change to the catalog, recorded by the database.

*Ray, 2026-11-10: "every catalog change", moderators included; revert
comes next.* A trigger on each catalog table writes a revision for every
row added, changed or removed, however it was written: the API, an import,
a merge, or SQL by hand. Who made it and what it came through (an import,
an accepted suggestion) are read from settings the app gives each
transaction (history.py); a change made outside the app has neither.

A revision keeps the columns that changed, as [before, after], and where
the row belongs: its source and recipe, or the ingredient or author it
hangs off, and whether that source is a family collection. history.py
decides who may read it from those.

Revision ID: 0040
Revises: 0039
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Table, and how its source is found: from the row itself (sources), its
# source_id, its recipe_id, or its edition_id; or none, for what isn't in a
# source.
TRACKED = {
    "sources": "self",
    "editions": "source",
    "episodes": "source",
    "issues": "source",
    "web_pages": "source",
    "source_credits": "source",
    "source_tags": "source",
    "recipes": "source",
    "recipe_locations": "source",
    "recipe_ingredients": "recipe",
    "ingredient_options": "recipe",
    "recipe_tags": "recipe",
    "purchase_links": "edition",
    "substitutions": "none",
    "authors": "none",
    "author_links": "none",
    "ingredients": "none",
    "ingredient_aliases": "none",
    "tags": "none",
}

FUNCTION = r"""
CREATE FUNCTION record_revision() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  how text := TG_ARGV[0];
  old_row jsonb := CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END;
  new_row jsonb := CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END;
  row_ jsonb := coalesce(new_row, old_row);
  noise text[] := ARRAY['created_at', 'updated_at', 'match_key', 'name_key',
                        'wikidata_checked_at', 'archive_tried_at'];
  diff jsonb := '{}';
  k text;
  src uuid;
  rec uuid;
  parent uuid;
  fam boolean;
  actor text := nullif(current_setting('openlarder.actor', true), '');
  change text := nullif(current_setting('openlarder.change', true), '');
BEGIN
  FOR k IN SELECT jsonb_object_keys(row_) LOOP
    CONTINUE WHEN k = ANY(noise);
    IF old_row IS DISTINCT FROM NULL AND new_row IS DISTINCT FROM NULL THEN
      IF old_row -> k IS DISTINCT FROM new_row -> k THEN
        diff := diff || jsonb_build_object(k, jsonb_build_array(old_row -> k, new_row -> k));
      END IF;
    ELSIF row_ -> k <> 'null'::jsonb THEN
      diff := diff || jsonb_build_object(
        k, jsonb_build_array(old_row -> k, new_row -> k));
    END IF;
  END LOOP;
  IF diff = '{}' THEN
    RETURN NULL;
  END IF;

  IF how = 'self' THEN
    src := (row_ ->> 'id')::uuid;
  ELSIF how = 'source' THEN
    src := (row_ ->> 'source_id')::uuid;
  ELSIF how = 'edition' THEN
    SELECT source_id INTO src FROM editions WHERE id = (row_ ->> 'edition_id')::uuid;
  END IF;
  IF TG_TABLE_NAME = 'recipes' THEN
    rec := (row_ ->> 'id')::uuid;
  ELSIF how = 'recipe' OR TG_TABLE_NAME IN ('recipe_locations', 'substitutions') THEN
    rec := coalesce(row_ ->> 'recipe_id', row_ ->> 'from_recipe_id',
                    row_ ->> 'to_recipe_id')::uuid;
  END IF;
  IF src IS NULL AND rec IS NOT NULL THEN
    SELECT source_id INTO src FROM recipes WHERE id = rec;
    -- Removed with its recipe, which is gone already: as its recipe's
    -- revision recorded it.
    IF src IS NULL THEN
      SELECT source_id INTO src FROM revisions
      WHERE table_name = 'recipes' AND record_id = rec AND source_id IS NOT NULL
      ORDER BY id DESC LIMIT 1;
    END IF;
  END IF;
  parent := CASE TG_TABLE_NAME
    WHEN 'author_links' THEN (row_ ->> 'author_id')::uuid
    WHEN 'ingredient_aliases' THEN (row_ ->> 'ingredient_id')::uuid
    WHEN 'ingredient_options' THEN (row_ ->> 'ingredient_id')::uuid
    WHEN 'substitutions' THEN (row_ ->> 'from_ingredient_id')::uuid
  END;
  IF TG_TABLE_NAME = 'sources' THEN
    fam := row_ ->> 'kind' = 'family';
  ELSIF src IS NOT NULL THEN
    SELECT kind = 'family' INTO fam FROM sources WHERE id = src;
    IF fam IS NULL THEN
      SELECT family INTO fam FROM revisions
      WHERE table_name = 'sources' AND record_id = src ORDER BY id DESC LIMIT 1;
    END IF;
  END IF;

  INSERT INTO revisions (change_id, user_id, via, table_name, record_id, action,
                         source_id, recipe_id, parent_id, family, changes)
  VALUES (
    coalesce(change::uuid, md5(txid_current()::text)::uuid),
    (SELECT id FROM users WHERE id = actor::uuid),
    nullif(current_setting('openlarder.via', true), ''),
    TG_TABLE_NAME,
    CASE WHEN row_ ? 'id' THEN (row_ ->> 'id')::uuid END,
    lower(left(TG_OP, 1)),
    src, rec, parent,
    -- Unknown means it can't be shown as public.
    coalesce(fam, how <> 'none'),
    diff
  );
  RETURN NULL;
END
$$;
"""


def upgrade() -> None:
    op.create_table(
        "revisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("change_id", sa.UUID(), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("via", sa.Text(), nullable=True),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("recipe_id", sa.UUID(), nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("family", sa.Boolean(), nullable=False),
        sa.Column("changes", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("action IN ('i', 'u', 'd')", name=op.f("ck_revisions_action_known")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_revisions_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_revisions")),
    )
    op.create_index(op.f("ix_revisions_change_id"), "revisions", ["change_id"])
    op.create_index(op.f("ix_revisions_user_id"), "revisions", ["user_id"])
    op.create_index("ix_revisions_record", "revisions", ["table_name", "record_id"])
    op.create_index(op.f("ix_revisions_source_id"), "revisions", ["source_id"])
    op.create_index(op.f("ix_revisions_recipe_id"), "revisions", ["recipe_id"])
    op.create_index(op.f("ix_revisions_parent_id"), "revisions", ["parent_id"])
    op.execute(FUNCTION)
    for table, how in TRACKED.items():
        op.execute(
            f"CREATE TRIGGER record_revision AFTER INSERT OR UPDATE OR DELETE ON {table}"
            f" FOR EACH ROW EXECUTE FUNCTION record_revision('{how}')"
        )


def downgrade() -> None:
    for table in TRACKED:
        op.execute(f"DROP TRIGGER record_revision ON {table}")
    op.execute("DROP FUNCTION record_revision()")
    op.drop_table("revisions")
