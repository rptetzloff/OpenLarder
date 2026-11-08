"""Who sees what: private family collections.

A family collection can be private, seen only by its owner (migration 0026;
household groups come next). Everything else is public. Every read that
returns sources, recipes or ingredients narrows by these conditions, and
every write to a recipe checks may_edit. A private collection is not shown
to admins either: it isn't theirs.

An ingredient is matched from every recipe's lines, private ones included,
so a private recipe can bring a name into being ("Grandma's spice mix").
Such an ingredient is hidden from anyone who can't see a recipe using it:
an ingredient shows when nothing uses it yet, or a recipe they can see does.
Authors are treated the same way, by the sources crediting them.

The database does not enforce any of this; tests/test_privacy.py asks every
GET route in the app as other people and fails on anything private it
finds, so a new route has to answer it.
"""

from sqlalchemy import ColumnElement, exists, false, or_, select
from sqlalchemy.orm import aliased

from openlarder.models import (
    Author,
    Ingredient,
    IngredientOption,
    Recipe,
    Source,
    SourceCredit,
    User,
)


def sources_seen_by(viewer: User | None) -> ColumnElement[bool]:
    """Every public source, and the viewer's own private ones."""
    if viewer is None:
        return Source.private.is_(false())
    return or_(Source.private.is_(false()), Source.owner_id == viewer.id)


def seen_source_ids(viewer: User | None):
    return select(Source.id).where(sources_seen_by(viewer))


def recipes_seen_by(viewer: User | None) -> ColumnElement[bool]:
    return Recipe.source_id.in_(seen_source_ids(viewer))


def options_seen_by(viewer: User | None) -> ColumnElement[bool]:
    return IngredientOption.recipe_id.in_(select(Recipe.id).where(recipes_seen_by(viewer)))


def ingredients_seen_by(viewer: User | None) -> ColumnElement[bool]:
    """Ingredients nothing uses yet, and those a recipe the viewer can see
    uses."""
    # Aliased, so a query already joining options doesn't swallow these.
    option = aliased(IngredientOption)
    used = option.ingredient_id == Ingredient.id
    seen = option.recipe_id.in_(select(Recipe.id).where(recipes_seen_by(viewer)))
    return or_(~exists().where(used), exists().where(used, seen))


def authors_seen_by(viewer: User | None) -> ColumnElement[bool]:
    """As for ingredients: authors nothing credits yet, and those a source
    the viewer can see credits."""
    credit = aliased(SourceCredit)
    credited = credit.author_id == Author.id
    return or_(
        ~exists().where(credited),
        exists().where(credited, credit.source_id.in_(seen_source_ids(viewer))),
    )


def can_see(viewer: User | None, source: Source) -> bool:
    return not source.private or (viewer is not None and source.owner_id == viewer.id)


def may_edit(user: User, source: Source) -> bool:
    """A family collection is its owner's to change, and an admin's too once
    it's public; everything else is an admin's."""
    if source.kind == "family":
        return source.owner_id == user.id or (user.is_admin and not source.private)
    return user.is_admin
