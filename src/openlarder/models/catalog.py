"""The catalog: books, their editions, the recipes in them, and ingredients.

Everything here is open data (ODbL). It records facts about recipes -- title,
page, ingredient lines, tags -- never a book's instructions or headnotes.
See DATA_MODEL.svg for the shape.

Rules the schema enforces rather than leaves to the application:

- A recipe page joins a recipe to an edition *of the same work*. recipe_locations
  carries source_id with composite foreign keys to both sides, so a page in the
  wrong book cannot be written.
- No recipe_locations row means the recipe is not in that edition. A row with a
  null page means it is, but nobody has recorded where yet.
- An ingredient option points at a canonical ingredient, a sub-recipe, or
  neither (not matched yet) -- never both. Ranks are unique within a line.
- A work credit points at one author and keeps the name as printed. One
  author can't be credited twice in the same role on the same book, and an
  author still credited somewhere can't be deleted.
- A substitution has exactly one thing on each side, never the same thing
  twice, and its reason can only be a diet tag. A page needs an edition.

Not enforced: cycles in the ingredient hierarchy or in sub-recipes longer
than one step. A recipe cannot list itself and an ingredient cannot be its
own parent, but A -> B -> A is the application's to refuse. Nor that every
line has an option, or that ranks run 1, 2, 3 without gaps; readers order by
rank and treat the lowest as first.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from openlarder.author_names import name_key
from openlarder.models.base import Base, Timestamps, uuid_pk


class TagKind(enum.StrEnum):
    COURSE = "course"
    CUISINE = "cuisine"
    DIET = "diet"
    TECHNIQUE = "technique"


tag_kind = ENUM(
    TagKind, name="tag_kind", values_callable=lambda e: [m.value for m in e], create_type=False
)


def _fk(target: str, *, ondelete: str, nullable: bool = False) -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


def _trgm(table: str, column: str) -> Index:
    """A trigram index, for fuzzy matching as someone types."""
    return Index(
        f"ix_{table}_{column}_trgm",
        column,
        postgresql_using="gin",
        postgresql_ops={column: "gin_trgm_ops"},
    )


class Source(Timestamps, Base):
    """Where recipes come from: a book, across every printing of it, a
    website, a magazine or newspaper, a TV show, podcast or video channel, a
    social media account, a product's packaging, or a family's collection.

    Each kind has its own parts in its own table: a book's are its editions,
    a website's and a social media account's its pages, a magazine's its
    issues, a show's its episodes. Packaging and family collections have
    none: their recipes are just in them. Migration 0019; Ray, 2026-11-08.

    A family collection has an owner and can be private: seen only by its
    owner (migration 0026). visibility.py is where that is applied.
    """

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("title <> ''", name="title_not_empty"),
        CheckConstraint(
            "kind IN ('book', 'website', 'magazine', 'newspaper', 'tv_show', 'podcast',"
            " 'video_channel', 'social', 'packaging', 'family')",
            name="kind_known",
        ),
        CheckConstraint("(kind = 'website') = (host IS NOT NULL)", name="host_for_websites"),
        CheckConstraint("host <> ''", name="host_not_empty"),
        CheckConstraint("NOT paywalled OR kind = 'website'", name="paywalled_websites_only"),
        CheckConstraint("(kind = 'family') = (owner_id IS NOT NULL)", name="owner_for_family"),
        CheckConstraint("NOT private OR kind = 'family'", name="private_only_family"),
        CheckConstraint(
            "(kind = 'family') = (acknowledged_at IS NOT NULL)", name="family_acknowledged"
        ),
        Index("ix_sources_owner_id", "owner_id"),
        # The target of source_groups' key, which only allows a family
        # collection (migration 0027).
        UniqueConstraint("id", "kind"),
        _trgm("sources", "title"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="book")
    # A website's, without "www." ("smittenkitchen.com"); one source per site
    # (migration 0020).
    host: Mapped[str | None] = mapped_column(Text, unique=True)
    # A website behind a subscription: linked, never copied.
    paywalled: Mapped[bool] = mapped_column(nullable=False, server_default=false())
    # A family collection's: who added it, whether only they see it, and
    # when they ticked that they understand what the site keeps.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    private: Mapped[bool] = mapped_column(nullable=False, server_default=false())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text)
    open_library_work_id: Mapped[str | None] = mapped_column(Text, unique=True)


class Author(Timestamps, Base):
    """A person or an organisation credited on books ("America's Test Kitchen")."""

    __tablename__ = "authors"
    __table_args__ = (
        CheckConstraint("name <> ''", name="name_not_empty"),
        CheckConstraint("kind IN ('person', 'organisation')", name="kind_known"),
        CheckConstraint("wikidata_id ~ '^Q[1-9][0-9]*$'", name="wikidata_id_format"),
        Index("ix_authors_name_key", "name_key"),
        _trgm("authors", "name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Not unique: two cooks can share a name. Duplicates are merged by hand.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # The name as compared (author_names.name_key), kept with it: "Katarina
    # Čermelj" and "Cermelj, Katarina" share one (migration 0022).
    name_key: Mapped[str] = mapped_column(Text, nullable=False)

    @validates("name")
    def _keep_key(self, _key: str, name: str) -> str:
        self.name_key = name_key(name)
        return name

    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="person")
    open_library_author_id: Mapped[str | None] = mapped_column(Text, unique=True)
    wikidata_id: Mapped[str | None] = mapped_column(Text, unique=True)
    # Facts from Wikidata (CC0), as of wikidata_checked_at (wikidata.py).
    # Years only: most authors are living people, and a year is all the page
    # says. For an organisation, born is when it was founded.
    born_year: Mapped[int | None] = mapped_column(SmallInteger)
    died_year: Mapped[int | None] = mapped_column(SmallInteger)
    # Country of citizenship, or an organisation's country, as Wikidata
    # labels it ("United States"); two at most, joined by " and ".
    country: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    # When Wikidata was last asked; null if never. Asked again after a while
    # even when nothing was found, since items are added.
    wikidata_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthorLink(Timestamps, Base):
    """The author's own website or social account."""

    __tablename__ = "author_links"
    __table_args__ = (
        UniqueConstraint("author_id", "url"),
        CheckConstraint("url <> ''", name="url_not_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    author_id: Mapped[uuid.UUID] = _fk("authors.id", ondelete="CASCADE")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)


class SourceCredit(Timestamps, Base):
    """One name on a book's cover or title page, in the order printed."""

    __tablename__ = "source_credits"
    __table_args__ = (
        UniqueConstraint("source_id", "position"),
        # The same person credited twice in one role is a duplicate; as author
        # and photographer is two credits.
        UniqueConstraint("source_id", "author_id", "role"),
        CheckConstraint("credited_as <> ''", name="credited_as_not_empty"),
        CheckConstraint(
            "role IN ('author', 'editor', 'contributor', 'photographer', 'illustrator',"
            " 'translator')",
            name="role_known",
        ),
        Index("ix_source_credits_author_id", "author_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id", ondelete="CASCADE")
    # RESTRICT: an author still credited is merged into another, not deleted.
    author_id: Mapped[uuid.UUID] = _fk("authors.id", ondelete="RESTRICT")
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="author")
    # The name as the book prints it ("Sarah Ballantyne, PhD"), which can
    # differ from the author's canonical name.
    credited_as: Mapped[str] = mapped_column(Text, nullable=False)


class Edition(Timestamps, Base):
    """One printing of a work: its own ISBN, publisher, and page numbers."""

    __tablename__ = "editions"
    __table_args__ = (
        # The target of recipe_locations' composite key.
        UniqueConstraint("source_id", "id"),
        # ISBN-13 only; ISBN-10s are converted on the way in. Nullable because
        # older books have none. The checksum is checked by the application.
        CheckConstraint("isbn13 ~ '^97[89][0-9]{10}$'", name="isbn13_format"),
        CheckConstraint("published_year BETWEEN 1400 AND 2200", name="published_year_range"),
        CheckConstraint("open_library_cover_id > 0", name="open_library_cover_id_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id", ondelete="CASCADE")
    # Only when it differs from the work's, e.g. a UK edition retitled.
    title: Mapped[str | None] = mapped_column(Text)
    isbn13: Mapped[str | None] = mapped_column(Text, unique=True)
    publisher: Mapped[str | None] = mapped_column(Text)
    published_year: Mapped[int | None] = mapped_column(SmallInteger)
    open_library_edition_id: Mapped[str | None] = mapped_column(Text, unique=True)
    # An object-store key, not a URL, so the bucket can move. Unused until
    # covers are stored; until then they are shown from Open Library.
    cover_key: Mapped[str | None] = mapped_column(Text)
    open_library_cover_id: Mapped[int | None] = mapped_column(Integer)


class PurchaseLink(Timestamps, Base):
    __tablename__ = "purchase_links"
    __table_args__ = (
        UniqueConstraint("edition_id", "retailer"),
        CheckConstraint("retailer <> ''", name="retailer_not_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    edition_id: Mapped[uuid.UUID] = _fk("editions.id", ondelete="CASCADE")
    retailer: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)


class Recipe(Timestamps, Base):
    __tablename__ = "recipes"
    __table_args__ = (
        UniqueConstraint("source_id", "id"),
        CheckConstraint("title <> ''", name="title_not_empty"),
        # Not unique: one book can have two recipes called "Vinaigrette".
        # Duplicate detection warns on title + work; it does not refuse.
        Index("ix_recipes_source_id_title", "source_id", "title"),
        Index("ix_recipes_created_by", "created_by"),
        _trgm("recipes", "title"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id", ondelete="CASCADE")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Only where the publisher posted the recipe itself.
    online_url: Mapped[str | None] = mapped_column(Text)
    # Who added it, so they can see its flags. Null for recipes added before
    # migration 0012, or whose account was deleted.
    created_by: Mapped[uuid.UUID | None] = _fk("users.id", ondelete="SET NULL", nullable=True)


class WebPage(Timestamps, Base):
    """A page of a website source, where a recipe is (migration 0020)."""

    __tablename__ = "web_pages"
    __table_args__ = (
        # The target of recipe_locations' composite key.
        UniqueConstraint("source_id", "id"),
        CheckConstraint("url <> ''", name="url_not_empty"),
        CheckConstraint("archive_url <> ''", name="archive_url_not_empty"),
        CheckConstraint("(archive_url IS NULL) = (archived_at IS NULL)", name="archived_together"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id", ondelete="CASCADE")
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # The Internet Archive's copy, and when it was made (archive.py;
    # migration 0021). archive_tried_at: the last time one was asked for.
    archive_url: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_tried_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Marked by an admin when the page no longer has the recipe; its copy
    # is offered instead.
    gone: Mapped[bool] = mapped_column(nullable=False, server_default=false())


class Issue(Timestamps, Base):
    """An issue of a magazine or newspaper source, where a recipe is, at a
    page: named as the cover names it ("May 2024"), or for a newspaper by
    its date (migration 0023)."""

    __tablename__ = "issues"
    __table_args__ = (
        # The target of recipe_locations' composite key.
        UniqueConstraint("source_id", "id"),
        Index("uq_issues_source_id_label", "source_id", text("lower(label)"), unique=True),
        CheckConstraint("label <> ''", name="label_not_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id", ondelete="CASCADE")
    label: Mapped[str] = mapped_column(Text, nullable=False)
    published_on: Mapped[date | None] = mapped_column(Date)


class Episode(Timestamps, Base):
    """An episode of a TV show, podcast or video channel, where a recipe is:
    known by its season and number, its title, or for a video its address,
    whichever are given (migration 0024)."""

    __tablename__ = "episodes"
    __table_args__ = (
        # The target of recipe_locations' composite key.
        UniqueConstraint("source_id", "id"),
        UniqueConstraint("source_id", "url"),
        # Season 2, episode 5 once per show; an episode without a season once too.
        Index(
            "uq_episodes_source_id_season_number",
            "source_id",
            text("coalesce(season, -1)"),
            "number",
            unique=True,
            postgresql_where=text("number IS NOT NULL"),
        ),
        CheckConstraint("num_nonnulls(number, title, url) >= 1", name="named"),
        CheckConstraint("season IS NULL OR number IS NOT NULL", name="season_needs_number"),
        CheckConstraint("season >= 0 AND number >= 0", name="numbers_not_negative"),
        CheckConstraint("title <> ''", name="title_not_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id", ondelete="CASCADE")
    season: Mapped[int | None] = mapped_column(Integer)
    number: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text)
    # A video's or podcast episode's address, as web.page keeps it.
    url: Mapped[str | None] = mapped_column(Text)
    aired_on: Mapped[date | None] = mapped_column(Date)


class RecipeLocation(Timestamps, Base):
    """Where a recipe is in its source: an edition of a book, a web page, an
    issue of a magazine or newspaper, or an episode, exactly one (migrations
    0020, 0023, 0024); a page goes with an edition or an issue, and a time
    with an episode."""

    __tablename__ = "recipe_locations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "recipe_id"], ["recipes.source_id", "recipes.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["source_id", "edition_id"], ["editions.source_id", "editions.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["source_id", "web_page_id"],
            ["web_pages.source_id", "web_pages.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["source_id", "issue_id"], ["issues.source_id", "issues.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["source_id", "episode_id"], ["episodes.source_id", "episodes.id"], ondelete="CASCADE"
        ),
        UniqueConstraint("recipe_id", "edition_id"),
        UniqueConstraint("recipe_id", "issue_id"),
        UniqueConstraint("recipe_id", "episode_id"),
        UniqueConstraint("recipe_id", "web_page_id"),
        CheckConstraint("page <> ''", name="page_not_empty"),
        CheckConstraint(
            "num_nonnulls(edition_id, web_page_id, issue_id, episode_id) = 1", name="one_place"
        ),
        CheckConstraint(
            "at_seconds IS NULL OR (episode_id IS NOT NULL AND at_seconds >= 0)",
            name="time_needs_an_episode",
        ),
        CheckConstraint(
            "page IS NULL OR edition_id IS NOT NULL OR issue_id IS NOT NULL",
            name="page_needs_a_printing",
        ),
        Index("ix_recipe_locations_edition_id", "edition_id"),
        Index("ix_recipe_locations_web_page_id", "web_page_id"),
        Index("ix_recipe_locations_issue_id", "issue_id"),
        Index("ix_recipe_locations_episode_id", "episode_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    edition_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    web_page_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    issue_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    episode_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Text, because books number pages "xii" and recipes span "112-13".
    # Null means in this edition, page not yet recorded.
    page: Mapped[str | None] = mapped_column(Text)
    # Seconds into an episode where the recipe starts.
    at_seconds: Mapped[int | None] = mapped_column(Integer)


class Ingredient(Timestamps, Base):
    """One canonical ingredient ("green onion"), whatever a book calls it."""

    __tablename__ = "ingredients"
    __table_args__ = (
        CheckConstraint("name <> ''", name="name_not_empty"),
        CheckConstraint("parent_id <> id", name="not_own_parent"),
        CheckConstraint("match_key <> ''", name="match_key_not_empty"),
        Index("uq_ingredients_name", text("lower(name)"), unique=True),
        Index("ix_ingredients_parent_id", "parent_id"),
        _trgm("ingredients", "name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # What lines are matched by: the name without case, plurals or
    # punctuation (migration 0015). ingredients.match_key makes it.
    match_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # What to search for at a grocer, when it differs from the name.
    shopping_term: Mapped[str | None] = mapped_column(Text)
    # Broader ingredient, for search: aged cheddar -> cheddar -> cheese.
    # RESTRICT: a parent is merged away, not deleted out from under children.
    parent_id: Mapped[uuid.UUID | None] = _fk("ingredients.id", ondelete="RESTRICT", nullable=True)


class IngredientAlias(Timestamps, Base):
    """Another name for an ingredient ("scallion"), optionally regional."""

    __tablename__ = "ingredient_aliases"
    __table_args__ = (
        CheckConstraint("name <> ''", name="name_not_empty"),
        CheckConstraint("region IN ('US', 'UK', 'AU')", name="region_known"),
        # One meaning per name per region. NULLS NOT DISTINCT, so an unmarked
        # alias is unique too rather than duplicable without limit.
        Index(
            "uq_ingredient_aliases_name_region",
            text("lower(name)"),
            "region",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("match_key <> ''", name="match_key_not_empty"),
        # Unmarked aliases match lines (migration 0016), so one key, one meaning.
        Index(
            "uq_ingredient_aliases_match_key",
            "match_key",
            unique=True,
            postgresql_where=text("region IS NULL"),
        ),
        Index("ix_ingredient_aliases_ingredient_id", "ingredient_id"),
        _trgm("ingredient_aliases", "name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    ingredient_id: Mapped[uuid.UUID] = _fk("ingredients.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Unmarked aliases match lines too, by the same key as ingredients
    # (migration 0016); ingredients.py keeps one key from meaning two things.
    match_key: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)


class RecipeIngredient(Timestamps, Base):
    """One ingredient of a recipe, named as the book names it, without an amount.

    OpenLarder records what goes in a recipe so it can be found by
    ingredient, not how much or what to do with it (migration 0011). What the
    line names lives on its options: one for most lines, more for a line like
    "grapeseed oil or olive oil".
    """

    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        UniqueConstraint("recipe_id", "position"),
        # The target of ingredient_options' composite key.
        UniqueConstraint("recipe_id", "id"),
        CheckConstraint("original_text <> ''", name="original_text_not_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_id: Mapped[uuid.UUID] = _fk("recipes.id", ondelete="CASCADE")
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # The ingredient as the book names it ("caster sugar"), kept as typed so
    # a mapping can be corrected later without re-entry.
    original_text: Mapped[str] = mapped_column(Text, nullable=False)


class IngredientOption(Timestamps, Base):
    """One choice on an ingredient line: rank 1 is the book's first, the rest fallbacks."""

    __tablename__ = "ingredient_options"
    __table_args__ = (
        # Carries the line's recipe_id so the CHECK below can see it. Named by
        # hand: the convention's name runs past Postgres' 63 characters.
        ForeignKeyConstraint(
            ["recipe_id", "recipe_ingredient_id"],
            ["recipe_ingredients.recipe_id", "recipe_ingredients.id"],
            ondelete="CASCADE",
            name="fk_ingredient_options_line",
        ),
        UniqueConstraint("recipe_ingredient_id", "rank"),
        CheckConstraint("rank >= 1", name="rank_positive"),
        CheckConstraint("name <> ''", name="name_not_empty"),
        CheckConstraint(
            "num_nonnulls(ingredient_id, sub_recipe_id) <= 1", name="one_target_at_most"
        ),
        CheckConstraint("sub_recipe_id <> recipe_id", name="not_own_sub_recipe"),
        # Counting the recipes that use an ingredient reads it in order
        # (migration 0028).
        Index("ix_ingredient_options_ingredient_id_recipe_id", "ingredient_id", "recipe_id"),
        Index("ix_ingredient_options_sub_recipe_id", "sub_recipe_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_ingredient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # This option as the line names it ("Olive Oil"), so an option nothing
    # matched yet can still be matched later.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # RESTRICT on both: an ingredient in use is merged, and a recipe used as a
    # component cannot vanish from the recipes that use it.
    ingredient_id: Mapped[uuid.UUID | None] = _fk(
        "ingredients.id", ondelete="RESTRICT", nullable=True
    )
    sub_recipe_id: Mapped[uuid.UUID | None] = _fk("recipes.id", ondelete="RESTRICT", nullable=True)


class Tag(Timestamps, Base):
    __tablename__ = "tags"
    __table_args__ = (
        CheckConstraint("name <> ''", name="name_not_empty"),
        Index("uq_tags_kind_name", "kind", text("lower(name)"), unique=True),
        # The target of substitutions' composite key, which pins it to diets.
        UniqueConstraint("kind", "id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[TagKind] = mapped_column(tag_kind, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class SourceTag(Base):
    """A tag on a whole book, inherited by every recipe in it."""

    __tablename__ = "source_tags"
    __table_args__ = (
        PrimaryKeyConstraint("source_id", "tag_id"),
        Index("ix_source_tags_tag_id", "tag_id"),
    )

    source_id: Mapped[uuid.UUID] = _fk("sources.id", ondelete="CASCADE")
    tag_id: Mapped[uuid.UUID] = _fk("tags.id", ondelete="CASCADE")


class RecipeTag(Base):
    __tablename__ = "recipe_tags"
    __table_args__ = (
        PrimaryKeyConstraint("recipe_id", "tag_id"),
        Index("ix_recipe_tags_tag_id", "tag_id"),
    )

    recipe_id: Mapped[uuid.UUID] = _fk("recipes.id", ondelete="CASCADE")
    tag_id: Mapped[uuid.UUID] = _fk("tags.id", ondelete="CASCADE")


class Substitution(Timestamps, Base):
    """One thing that can stand in for another, usually for a diet.

    Each side is an ingredient or a recipe, so a dairy-free butter can stand in
    for butter, or one book's flour blend for another's. One-way: the reverse
    swap is its own row, because it often doesn't hold.
    """

    __tablename__ = "substitutions"
    __table_args__ = (
        CheckConstraint("num_nonnulls(from_ingredient_id, from_recipe_id) = 1", name="one_from"),
        CheckConstraint("num_nonnulls(to_ingredient_id, to_recipe_id) = 1", name="one_to"),
        CheckConstraint(
            "from_ingredient_id <> to_ingredient_id AND from_recipe_id <> to_recipe_id",
            name="not_itself",
        ),
        # A page only makes sense in an edition; contributed swaps have neither.
        CheckConstraint(
            "source_page IS NULL OR source_edition_id IS NOT NULL", name="page_needs_edition"
        ),
        CheckConstraint("source_page <> ''", name="source_page_not_empty"),
        CheckConstraint("diet_kind = 'diet'", name="diet_kind_is_diet"),
        CheckConstraint("note <> ''", name="note_not_empty"),
        ForeignKeyConstraint(
            ["diet_kind", "diet_tag_id"],
            ["tags.kind", "tags.id"],
            ondelete="RESTRICT",
            name="fk_substitutions_diet_tag",
        ),
        # The same swap, for the same diet, from the same source, once.
        Index(
            "uq_substitutions_swap",
            "from_ingredient_id",
            "from_recipe_id",
            "to_ingredient_id",
            "to_recipe_id",
            "diet_tag_id",
            "source_edition_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_substitutions_to_ingredient_id", "to_ingredient_id"),
        Index("ix_substitutions_from_recipe_id", "from_recipe_id"),
        Index("ix_substitutions_to_recipe_id", "to_recipe_id"),
        Index("ix_substitutions_diet_tag_id", "diet_tag_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # RESTRICT on ingredients, as elsewhere: one in use is merged, not
    # deleted. CASCADE on recipes: a swap involving a deleted recipe means
    # nothing.
    from_ingredient_id: Mapped[uuid.UUID | None] = _fk(
        "ingredients.id", ondelete="RESTRICT", nullable=True
    )
    from_recipe_id: Mapped[uuid.UUID | None] = _fk("recipes.id", ondelete="CASCADE", nullable=True)
    to_ingredient_id: Mapped[uuid.UUID | None] = _fk(
        "ingredients.id", ondelete="RESTRICT", nullable=True
    )
    to_recipe_id: Mapped[uuid.UUID | None] = _fk("recipes.id", ondelete="CASCADE", nullable=True)
    # Which diet the swap serves. Null for a swap that serves none in
    # particular, such as one for an ingredient that's hard to find.
    diet_tag_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Always 'diet'; it exists so the composite key above can only reach a
    # diet tag.
    diet_kind: Mapped[TagKind] = mapped_column(
        tag_kind, nullable=False, server_default=TagKind.DIET.value
    )
    # Printed in a book: the edition and page, since pages differ by edition.
    # Both null: contributed.
    source_edition_id: Mapped[uuid.UUID | None] = _fk(
        "editions.id", ondelete="RESTRICT", nullable=True
    )
    source_page: Mapped[str | None] = mapped_column(Text)
    # Free text, such as "3 tablespoons aquafaba per egg". Amounts are a note
    # on purpose, not structured data: Ray, 2026-11-06.
    note: Mapped[str | None] = mapped_column(Text)
