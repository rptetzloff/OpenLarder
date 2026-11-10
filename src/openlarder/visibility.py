"""Who sees what: private family collections.

A family collection can be private (migration 0026): seen by its owner, and
by the members of the household groups its owner shares it with (migration
0027). Everything else is public. Every read that returns sources, recipes
or ingredients narrows by these conditions, and every write to a recipe
checks may_edit. A private collection is not shown to admins either: it
isn't theirs.

In a group, a viewer sees what's shared with it; an editor or a group admin
also adds and changes its recipes. Renaming, deleting, making public and
sharing a collection stay with its owner (may_manage).

An ingredient is matched from every recipe's lines, private ones included,
so a private recipe can bring a name into being ("Grandma's spice mix").
Such an ingredient is hidden from anyone who can't see a recipe using it:
an ingredient shows when nothing uses it yet, or a recipe they can see does.
Authors are treated the same way, by the sources crediting them.

What a contributor adds is hidden the same way until a moderator approves
it (migration 0041): from everyone but them and moderators, ingredients and
authors only it uses included.

The database does not enforce any of this; tests/test_privacy.py asks every
GET route in the app as other people and fails on anything private it
finds, so a new route has to answer it.
"""

from sqlalchemy import ColumnElement, and_, exists, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from openlarder.models import (
    Author,
    GroupMember,
    Ingredient,
    IngredientOption,
    Recipe,
    Source,
    SourceCredit,
    SourceGroup,
    User,
)

# Group roles that may add and change recipes in what's shared with them.
EDITING_ROLES = ("edit", "admin")


def _shared_with(user: User):
    """The IDs of sources shared with a group the user is in."""
    member = and_(GroupMember.group_id == SourceGroup.group_id, GroupMember.user_id == user.id)
    return select(SourceGroup.source_id).join(GroupMember, member)


def _reviewed(model, viewer: User | None) -> ColumnElement[bool]:
    """Published, or waiting and the viewer's own, or the viewer reviews:
    what a contributor adds is hidden from everyone else until a moderator
    approves it (migration 0041)."""
    if viewer is None:
        return model.review == "published"
    if viewer.may_edit:
        return true()
    return or_(model.review == "published", model.created_by == viewer.id)


def sources_seen_by(viewer: User | None) -> ColumnElement[bool]:
    """Every public source, the viewer's own private ones, and those shared
    with a group they're in; of those, the ones published or theirs to see
    waiting for review."""
    if viewer is None:
        return and_(Source.private.is_(false()), Source.review == "published")
    return and_(
        or_(
            Source.private.is_(false()),
            Source.owner_id == viewer.id,
            Source.id.in_(_shared_with(viewer)),
        ),
        _reviewed(Source, viewer),
    )


def seen_source_ids(viewer: User | None):
    return select(Source.id).where(sources_seen_by(viewer))


# The rest is written in terms of what the viewer can't see: a handful of
# private collections against a catalog of thousands, so each condition is a
# small set checked once rather than a large one checked per row. Asking
# per row whether a recipe's source was among those seen made the
# ingredient list 2.5 times slower on a production-sized catalog (#64).


def _hidden_source_ids(viewer: User | None):
    return select(Source.id).where(~sources_seen_by(viewer))


def _hidden_recipe_ids(viewer: User | None):
    return select(Recipe.id).where(
        or_(Recipe.source_id.in_(_hidden_source_ids(viewer)), ~_reviewed(Recipe, viewer))
    )


def hidden_source_ids(viewer: User | None):
    """The sources the viewer can't see: private, or waiting and not theirs."""
    return _hidden_source_ids(viewer)


def hidden_recipe_ids(viewer: User | None):
    return _hidden_recipe_ids(viewer)


def recipes_seen_by(viewer: User | None) -> ColumnElement[bool]:
    return and_(Recipe.source_id.not_in(_hidden_source_ids(viewer)), _reviewed(Recipe, viewer))


def options_seen_by(viewer: User | None) -> ColumnElement[bool]:
    return IngredientOption.recipe_id.not_in(_hidden_recipe_ids(viewer))


def ingredients_seen_by(viewer: User | None) -> ColumnElement[bool]:
    """Ingredients nothing uses yet, and those a recipe the viewer can see
    uses: all but those only recipes they can't see use."""
    # Aliased, so a query already joining options doesn't swallow these.
    hidden_use = aliased(IngredientOption)
    seen_use = aliased(IngredientOption)
    # Starting from the hidden recipes' ingredients (usually none), then
    # dropping any a recipe the viewer can see also uses, by the index on
    # (ingredient_id, recipe_id): the other way round hashed every option.
    used_in_hidden = select(hidden_use.ingredient_id).where(
        # NOT IN with a NULL in the list matches nothing, and an option
        # naming a sub-recipe has no ingredient.
        hidden_use.ingredient_id.is_not(None),
        hidden_use.recipe_id.in_(_hidden_recipe_ids(viewer)),
    )
    used_where_seen = select(seen_use.ingredient_id).where(
        seen_use.ingredient_id.in_(used_in_hidden),
        seen_use.recipe_id.not_in(_hidden_recipe_ids(viewer)),
    )
    return Ingredient.id.not_in(used_in_hidden.except_(used_where_seen))


def authors_seen_by(viewer: User | None) -> ColumnElement[bool]:
    """As for ingredients: authors nothing credits yet, and those a source
    the viewer can see credits: all but those only hidden sources credit."""
    hidden_credit = aliased(SourceCredit)
    seen_credit = aliased(SourceCredit)
    only_hidden = (
        select(hidden_credit.author_id)
        .where(hidden_credit.source_id.in_(_hidden_source_ids(viewer)))
        .where(
            ~exists().where(
                seen_credit.author_id == hidden_credit.author_id,
                seen_credit.source_id.not_in(_hidden_source_ids(viewer)),
            )
        )
    )
    return Author.id.not_in(only_hidden)


async def _shared(
    session: AsyncSession, user: User, source: Source, roles: tuple[str, ...] | None = None
) -> bool:
    """Whether the source is shared with a group the user is in (with one of
    these roles)."""
    member = [
        SourceGroup.source_id == source.id,
        GroupMember.group_id == SourceGroup.group_id,
        GroupMember.user_id == user.id,
    ]
    if roles is not None:
        member.append(GroupMember.role.in_(roles))
    return bool(await session.scalar(select(exists().where(*member))))


def sees_waiting(viewer: User | None, row: Source | Recipe) -> bool:
    """Whether the viewer may see this source or recipe as far as review
    goes: published, theirs, or theirs to review."""
    if row.review == "published":
        return True
    return viewer is not None and (viewer.may_edit or row.created_by == viewer.id)


async def can_see(session: AsyncSession, viewer: User | None, source: Source) -> bool:
    if not sees_waiting(viewer, source):
        return False
    if not source.private:
        return True
    if viewer is None:
        return False
    return source.owner_id == viewer.id or await _shared(session, viewer, source)


def may_manage(user: User, source: Source) -> bool:
    """Rename, delete, make public or share a family collection: its owner,
    and a moderator once it's public."""
    return source.kind == "family" and (
        source.owner_id == user.id or (user.may_edit and not source.private)
    )


async def may_edit(session: AsyncSession, user: User, source: Source) -> bool:
    """Add recipes to a source. A family collection's: whoever may manage
    it, and the editors and admins of a group it's shared with; a book's:
    a contributor too, if it's published or theirs, and theirs wait for
    review; everything else's: a moderator or above."""
    if source.kind == "family":
        return may_manage(user, source) or await _shared(session, user, source, EDITING_ROLES)
    if user.may_edit:
        return True
    return (
        user.may_claim
        and source.kind == "book"
        and (source.review == "published" or source.created_by == user.id)
    )


def may_change_recipe(user: User, recipe: Recipe) -> bool:
    """Outside a family collection, a contributor changes and removes only
    their own recipes while they wait for review; a moderator, any."""
    return user.may_edit or (
        user.may_claim and recipe.created_by == user.id and recipe.review != "published"
    )


def may_tag_source(user: User, source: Source) -> bool:
    """A family collection's editors, a moderator, or the contributor who
    added the source while it waits for review."""
    return (
        source.kind == "family"
        or user.may_edit
        or (source.created_by == user.id and source.review != "published")
    )
