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

The database does not enforce any of this; tests/test_privacy.py asks every
GET route in the app as other people and fails on anything private it
finds, so a new route has to answer it.
"""

from sqlalchemy import ColumnElement, and_, exists, false, or_, select
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


def sources_seen_by(viewer: User | None) -> ColumnElement[bool]:
    """Every public source, the viewer's own private ones, and those shared
    with a group they're in."""
    if viewer is None:
        return Source.private.is_(false())
    return or_(
        Source.private.is_(false()),
        Source.owner_id == viewer.id,
        Source.id.in_(_shared_with(viewer)),
    )


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


async def can_see(session: AsyncSession, viewer: User | None, source: Source) -> bool:
    if not source.private:
        return True
    if viewer is None:
        return False
    return source.owner_id == viewer.id or await _shared(session, viewer, source)


def may_manage(user: User, source: Source) -> bool:
    """Rename, delete, make public or share a family collection: its owner,
    and an admin once it's public."""
    return source.kind == "family" and (
        source.owner_id == user.id or (user.is_admin and not source.private)
    )


async def may_edit(session: AsyncSession, user: User, source: Source) -> bool:
    """Add and change a source's recipes. A family collection's: whoever may
    manage it, and the editors and admins of a group it's shared with;
    everything else's: an admin."""
    if source.kind == "family":
        return may_manage(user, source) or await _shared(session, user, source, EDITING_ROLES)
    return user.is_admin
