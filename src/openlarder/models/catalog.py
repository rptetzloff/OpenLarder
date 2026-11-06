"""The catalog: books, their editions, the recipes in them, and ingredients.

Everything here is open data (ODbL). It records facts about recipes -- title,
page, ingredient lines, tags -- never a book's instructions or headnotes.
See DATA_MODEL.svg for the shape.

Rules the schema enforces rather than leaves to the application:

- A recipe page joins a recipe to an edition *of the same work*. recipe_pages
  carries work_id with composite foreign keys to both sides, so a page in the
  wrong book cannot be written.
- No recipe_pages row means the recipe is not in that edition. A row with a
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

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

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


class Work(Timestamps, Base):
    """One book, across every printing of it."""

    __tablename__ = "works"
    __table_args__ = (
        CheckConstraint("title <> ''", name="title_not_empty"),
        _trgm("works", "title"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
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
        _trgm("authors", "name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Not unique: two cooks can share a name. Duplicates are merged by hand.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="person")
    open_library_author_id: Mapped[str | None] = mapped_column(Text, unique=True)
    wikidata_id: Mapped[str | None] = mapped_column(Text, unique=True)


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


class WorkCredit(Timestamps, Base):
    """One name on a book's cover or title page, in the order printed."""

    __tablename__ = "work_credits"
    __table_args__ = (
        UniqueConstraint("work_id", "position"),
        # The same person credited twice in one role is a duplicate; as author
        # and photographer is two credits.
        UniqueConstraint("work_id", "author_id", "role"),
        CheckConstraint("credited_as <> ''", name="credited_as_not_empty"),
        CheckConstraint(
            "role IN ('author', 'editor', 'contributor', 'photographer', 'illustrator',"
            " 'translator')",
            name="role_known",
        ),
        Index("ix_work_credits_author_id", "author_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    work_id: Mapped[uuid.UUID] = _fk("works.id", ondelete="CASCADE")
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
        # The target of recipe_pages' composite key.
        UniqueConstraint("work_id", "id"),
        # ISBN-13 only; ISBN-10s are converted on the way in. Nullable because
        # older books have none. The checksum is checked by the application.
        CheckConstraint("isbn13 ~ '^97[89][0-9]{10}$'", name="isbn13_format"),
        CheckConstraint("published_year BETWEEN 1400 AND 2200", name="published_year_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    work_id: Mapped[uuid.UUID] = _fk("works.id", ondelete="CASCADE")
    # Only when it differs from the work's, e.g. a UK edition retitled.
    title: Mapped[str | None] = mapped_column(Text)
    isbn13: Mapped[str | None] = mapped_column(Text, unique=True)
    publisher: Mapped[str | None] = mapped_column(Text)
    published_year: Mapped[int | None] = mapped_column(SmallInteger)
    open_library_edition_id: Mapped[str | None] = mapped_column(Text, unique=True)
    # An object-store key, not a URL, so the bucket can move.
    cover_key: Mapped[str | None] = mapped_column(Text)


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
        UniqueConstraint("work_id", "id"),
        CheckConstraint("title <> ''", name="title_not_empty"),
        # Not unique: one book can have two recipes called "Vinaigrette".
        # Duplicate detection warns on title + work; it does not refuse.
        Index("ix_recipes_work_id_title", "work_id", "title"),
        _trgm("recipes", "title"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    work_id: Mapped[uuid.UUID] = _fk("works.id", ondelete="CASCADE")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Only where the publisher posted the recipe itself.
    online_url: Mapped[str | None] = mapped_column(Text)


class RecipePage(Timestamps, Base):
    __tablename__ = "recipe_pages"
    __table_args__ = (
        PrimaryKeyConstraint("recipe_id", "edition_id"),
        ForeignKeyConstraint(
            ["work_id", "recipe_id"], ["recipes.work_id", "recipes.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["work_id", "edition_id"], ["editions.work_id", "editions.id"], ondelete="CASCADE"
        ),
        CheckConstraint("page <> ''", name="page_not_empty"),
        Index("ix_recipe_pages_edition_id", "edition_id"),
    )

    recipe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    edition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    work_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Text, because books number pages "xii" and recipes span "112-13".
    # Null means in this edition, page not yet recorded.
    page: Mapped[str | None] = mapped_column(Text)


class Ingredient(Timestamps, Base):
    """One canonical ingredient ("green onion"), whatever a book calls it."""

    __tablename__ = "ingredients"
    __table_args__ = (
        CheckConstraint("name <> ''", name="name_not_empty"),
        CheckConstraint("parent_id <> id", name="not_own_parent"),
        Index("uq_ingredients_name", text("lower(name)"), unique=True),
        Index("ix_ingredients_parent_id", "parent_id"),
        _trgm("ingredients", "name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
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
        Index("ix_ingredient_aliases_ingredient_id", "ingredient_id"),
        _trgm("ingredient_aliases", "name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    ingredient_id: Mapped[uuid.UUID] = _fk("ingredients.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)


class RecipeIngredient(Timestamps, Base):
    """One ingredient line of a recipe, as the book printed it.

    What the line names lives on its options: one for most lines, more for a
    line like "grapeseed oil or olive oil".
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
    # Kept verbatim, so a mapping can be corrected later without re-entry.
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    # As parsed from original_text. Text, not numbers: "1 1/2", "a pinch".
    quantity: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    form: Mapped[str | None] = mapped_column(Text)  # canned, dried
    prep: Mapped[str | None] = mapped_column(Text)  # diced, toasted


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
        Index("ix_ingredient_options_ingredient_id", "ingredient_id"),
        Index("ix_ingredient_options_sub_recipe_id", "sub_recipe_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_ingredient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # This option as the line names it ("Olive Oil"), so an option nothing
    # matched yet can still be matched later.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Only when the book gives this option its own amount; otherwise the line's.
    quantity: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
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


class WorkTag(Base):
    """A tag on a whole book, inherited by every recipe in it."""

    __tablename__ = "work_tags"
    __table_args__ = (
        PrimaryKeyConstraint("work_id", "tag_id"),
        Index("ix_work_tags_tag_id", "tag_id"),
    )

    work_id: Mapped[uuid.UUID] = _fk("works.id", ondelete="CASCADE")
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
