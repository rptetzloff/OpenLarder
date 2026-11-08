"""TV shows, podcasts and video channels as sources, and recipes in episodes.

Step 4 of sources beyond books (TODO.md). A TV show, podcast or video
channel is a source; its parts are episodes, known by a season and number,
a title, or for a video its address, with the day it aired; a recipe is in
an episode, at a time in it when one is given. *Ray, 2026-11-08: "tv recipes
belong within episodes which belong to shows".*

A recipe's location is now an edition, a web page, an issue or an episode,
exactly one; a page goes with an edition or an issue, a time with an
episode.

Downgrade refuses while any show, podcast or channel exists, rather than
drop them.

Revision ID: 0024
Revises: 0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_sources_kind_known"), "sources", type_="check")
    op.create_check_constraint(op.f("ck_sources_kind_known"), "sources", f"kind IN ({kinds})")


def _one_place(columns: str) -> None:
    op.drop_constraint(op.f("ck_recipe_locations_one_place"), "recipe_locations", type_="check")
    op.create_check_constraint(
        op.f("ck_recipe_locations_one_place"),
        "recipe_locations",
        f"num_nonnulls({columns}) = 1",
    )


def upgrade() -> None:
    _kinds("'book', 'website', 'magazine', 'newspaper', 'tv_show', 'podcast', 'video_channel'")

    op.create_table(
        "episodes",
        sa.Column("id", UUID, server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("season", sa.Integer()),
        sa.Column("number", sa.Integer()),
        sa.Column("title", sa.Text()),
        sa.Column("url", sa.Text()),
        sa.Column("aired_on", sa.Date()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_episodes")),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_episodes_source_id_sources"),
            ondelete="CASCADE",
        ),
        # The target of recipe_locations' composite key.
        sa.UniqueConstraint("source_id", "id", name=op.f("uq_episodes_source_id_id")),
        sa.UniqueConstraint("source_id", "url", name=op.f("uq_episodes_source_id_url")),
        sa.CheckConstraint("num_nonnulls(number, title, url) >= 1", name=op.f("ck_episodes_named")),
        sa.CheckConstraint(
            "season IS NULL OR number IS NOT NULL", name=op.f("ck_episodes_season_needs_number")
        ),
        sa.CheckConstraint(
            "season >= 0 AND number >= 0", name=op.f("ck_episodes_numbers_not_negative")
        ),
        sa.CheckConstraint("title <> ''", name=op.f("ck_episodes_title_not_empty")),
    )
    # Season 2, episode 5 once per show; an episode without a season once too.
    op.create_index(
        "uq_episodes_source_id_season_number",
        "episodes",
        ["source_id", sa.text("coalesce(season, -1)"), "number"],
        unique=True,
        postgresql_where=sa.text("number IS NOT NULL"),
    )
    op.execute(
        "CREATE TRIGGER episodes_updated_at BEFORE UPDATE ON episodes "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    op.add_column("recipe_locations", sa.Column("episode_id", UUID))
    # Seconds into the episode where the recipe starts.
    op.add_column("recipe_locations", sa.Column("at_seconds", sa.Integer()))
    op.create_foreign_key(
        op.f("fk_recipe_locations_source_id_episode_id_episodes"),
        "recipe_locations",
        "episodes",
        ["source_id", "episode_id"],
        ["source_id", "id"],
        ondelete="CASCADE",
    )
    _one_place("edition_id, web_page_id, issue_id, episode_id")
    op.create_check_constraint(
        op.f("ck_recipe_locations_time_needs_an_episode"),
        "recipe_locations",
        "at_seconds IS NULL OR (episode_id IS NOT NULL AND at_seconds >= 0)",
    )
    op.create_unique_constraint(
        op.f("uq_recipe_locations_recipe_id_episode_id"),
        "recipe_locations",
        ["recipe_id", "episode_id"],
    )
    op.create_index(op.f("ix_recipe_locations_episode_id"), "recipe_locations", ["episode_id"])


def downgrade() -> None:
    held = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM sources WHERE kind IN ('tv_show', 'podcast', 'video_channel')"
        )
    )
    if held:
        raise RuntimeError(
            f"{held} TV shows, podcasts or video channels exist; remove them before downgrading."
        )
    op.drop_index(op.f("ix_recipe_locations_episode_id"), "recipe_locations")
    op.drop_constraint(
        op.f("uq_recipe_locations_recipe_id_episode_id"), "recipe_locations", type_="unique"
    )
    op.drop_constraint(
        op.f("ck_recipe_locations_time_needs_an_episode"), "recipe_locations", type_="check"
    )
    _one_place("edition_id, web_page_id, issue_id")
    op.drop_constraint(
        op.f("fk_recipe_locations_source_id_episode_id_episodes"),
        "recipe_locations",
        type_="foreignkey",
    )
    op.drop_column("recipe_locations", "at_seconds")
    op.drop_column("recipe_locations", "episode_id")
    op.drop_table("episodes")
    _kinds("'book', 'website', 'magazine', 'newspaper'")
