"""Saved recipes: the ones you want to cook, and the ones you have
(migration 0067). *SCOPING.md: "Saves, likes, 'want to cook' lists".*

A recipe is saved from its page as wanted, and marked cooked when it has
been; either can be taken off again. Search's "Only recipes I've saved"
(routers/search.py, saved=true) keeps to them.

Private, like the larder and the shelf: not in the edit history, the dumps
or the API's public reads. Shared the same way: its owner chooses which of
their household groups see it; a group's view members see it, its edit and
admin members save to it, mark things cooked and take them off. Sharing
stays its owner's. A recipe you can't see (a private collection's, not
shared with you) isn't shown to you on anyone's list.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select

from openlarder import visibility
from openlarder.auth import CurrentUser, SameOrigin
from openlarder.db import Session
from openlarder.models import (
    Group,
    GroupMember,
    Recipe,
    SavedGroup,
    SavedRecipe,
    Source,
    User,
)
from openlarder.routers.ingredients import UsedBy, with_pages

router = APIRouter(prefix="/api/saved", tags=["saved"])
MAX_SAVED = 2000
State = Literal["want", "cooked"]
# Group roles that change what's on a list shared with them.
EDITING_ROLES = ("edit", "admin")


class GroupRef(BaseModel):
    id: uuid.UUID
    name: str


class OtherList(BaseModel):
    """A list shared with you, and whether a recipe is on it."""

    owner_id: uuid.UUID
    owner_name: str | None
    editable: bool
    state: State | None = None


class IsSaved(BaseModel):
    recipe_id: uuid.UUID
    # None: not saved.
    state: State | None = None
    # The lists shared with you.
    others: list[OtherList] = []


class SavedEntry(UsedBy):
    state: State
    saved_at: datetime


class SharedList(BaseModel):
    owner_id: uuid.UUID
    owner_name: str | None
    # Whether you may change what's on it.
    editable: bool
    # The groups of yours it's shared through.
    through: list[GroupRef]
    recipes: list[SavedEntry]


class Saved(BaseModel):
    recipes: list[SavedEntry]
    # The groups yours is shared with, and your groups to choose from.
    shared_with: list[GroupRef] = []
    groups: list[GroupRef] = []
    # Other people's lists, shared with you.
    shared: list[SharedList] = []


class SaveIn(BaseModel):
    state: State = "want"


def _sharers(user: User):
    """Whose lists are shared with a group this person is in."""
    return (
        select(SavedGroup.user_id)
        .join(GroupMember, GroupMember.group_id == SavedGroup.group_id)
        .where(GroupMember.user_id == user.id)
    )


def saved_recipe_ids(user: User):
    """The recipes someone has saved, and those on lists shared with them."""
    return (
        select(SavedRecipe.recipe_id)
        .where(or_(SavedRecipe.user_id == user.id, SavedRecipe.user_id.in_(_sharers(user))))
        .distinct()
    )


async def _others(session, user: User) -> dict[uuid.UUID, SharedList]:
    """The lists shared with this person, by owner, without their recipes."""
    rows = await session.execute(
        select(SavedGroup.user_id, User.display_name, Group.id, Group.name, GroupMember.role)
        .join(GroupMember, GroupMember.group_id == SavedGroup.group_id)
        .join(Group, Group.id == SavedGroup.group_id)
        .join(User, User.id == SavedGroup.user_id)
        .where(GroupMember.user_id == user.id, SavedGroup.user_id != user.id)
        .order_by(func.lower(User.display_name), SavedGroup.user_id, func.lower(Group.name))
    )
    found: dict[uuid.UUID, SharedList] = {}
    for owner_id, owner_name, group_id, group_name, role in rows:
        shared = found.setdefault(
            owner_id,
            SharedList(
                owner_id=owner_id, owner_name=owner_name, editable=False, through=[], recipes=[]
            ),
        )
        shared.through.append(GroupRef(id=group_id, name=group_name))
        shared.editable = shared.editable or role in EDITING_ROLES
    return found


async def _recipes(
    session, viewer: User, owners: list[uuid.UUID]
) -> dict[uuid.UUID, list[SavedEntry]]:
    """Each owner's list, as cards, of the recipes the viewer can see: by
    source, then title."""
    rows = (
        await session.execute(
            select(Recipe.id, Recipe.title, Source.id, Source.title, SavedRecipe)
            .join(SavedRecipe, SavedRecipe.recipe_id == Recipe.id)
            .join(Source, Source.id == Recipe.source_id)
            .where(SavedRecipe.user_id.in_(owners), visibility.recipes_seen_by(viewer))
            .order_by(func.lower(Source.title), func.lower(Recipe.title), Recipe.id)
        )
    ).all()
    distinct = list({r[0]: r[:4] for r in rows}.values())
    cards = {c.id: c for c in await with_pages(session, distinct)}
    found: dict[uuid.UUID, list[SavedEntry]] = {}
    for recipe_id, _, _, _, saved in rows:
        found.setdefault(saved.user_id, []).append(
            SavedEntry(
                **cards[recipe_id].model_dump(), state=saved.state, saved_at=saved.created_at
            )
        )
    return found


@router.get("", response_model=Saved)
async def mine(user: CurrentUser, session: Session) -> Saved:
    """Your saved recipes, then the lists shared with you."""
    others = await _others(session, user)
    recipes = await _recipes(session, user, [user.id, *others])
    for owner_id, shared in others.items():
        shared.recipes = recipes.get(owner_id, [])
    my_groups = (
        await session.execute(
            select(Group.id, Group.name, SavedGroup.user_id)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .outerjoin(
                SavedGroup, (SavedGroup.group_id == Group.id) & (SavedGroup.user_id == user.id)
            )
            .where(GroupMember.user_id == user.id)
            .order_by(func.lower(Group.name))
        )
    ).all()
    return Saved(
        recipes=recipes.get(user.id, []),
        shared_with=[GroupRef(id=i, name=n) for i, n, shared in my_groups if shared],
        groups=[GroupRef(id=i, name=n) for i, n, _ in my_groups],
        shared=list(others.values()),
    )


class SharingIn(BaseModel):
    groups: list[uuid.UUID] = Field(default=[], max_length=50)


# Before /{recipe_id}, which would otherwise take "groups" for a recipe.
@router.put("/groups", response_model=Saved, dependencies=[SameOrigin])
async def share(body: SharingIn, user: CurrentUser, session: Session) -> Saved:
    """Choose which of your groups see your saved recipes; joining a group
    shares nothing by itself."""
    chosen = set(body.groups)
    in_them = set(
        await session.scalars(
            select(GroupMember.group_id).where(
                GroupMember.user_id == user.id, GroupMember.group_id.in_(chosen)
            )
        )
    )
    if chosen - in_them:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You can only share with groups you're in.")
    await session.execute(
        delete(SavedGroup).where(SavedGroup.user_id == user.id, SavedGroup.group_id.not_in(chosen))
    )
    held = set(
        await session.scalars(select(SavedGroup.group_id).where(SavedGroup.user_id == user.id))
    )
    for group_id in chosen - held:
        session.add(SavedGroup(user_id=user.id, group_id=group_id))
    await session.commit()
    return await mine(user, session)


async def _whose(session, user: User, owner: uuid.UUID | None) -> uuid.UUID:
    """The list to change: yours, or one shared with you that you may
    change. 404 for one you can't see, 403 for one you can only see."""
    if owner is None or owner == user.id:
        return user.id
    shared = (await _others(session, user)).get(owner)
    if shared is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such list.")
    if not shared.editable:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can see this list, but not change what's on it."
        )
    return owner


@router.get("/{recipe_id}", response_model=IsSaved)
async def one(recipe_id: uuid.UUID, user: CurrentUser, session: Session) -> IsSaved:
    """Whether you've saved a recipe, and whether it's on the lists shared
    with you."""
    others = await _others(session, user)
    rows = {
        row.user_id: row
        for row in await session.scalars(
            select(SavedRecipe)
            .join(Recipe, Recipe.id == SavedRecipe.recipe_id)
            .where(
                SavedRecipe.recipe_id == recipe_id,
                SavedRecipe.user_id.in_([user.id, *others]),
                visibility.recipes_seen_by(user),
            )
        )
    }
    return IsSaved(
        recipe_id=recipe_id,
        state=rows[user.id].state if user.id in rows else None,
        others=[
            OtherList(
                owner_id=o.owner_id,
                owner_name=o.owner_name,
                editable=o.editable,
                state=rows[o.owner_id].state if o.owner_id in rows else None,
            )
            for o in others.values()
        ],
    )


@router.put("/{recipe_id}", response_model=IsSaved, dependencies=[SameOrigin])
async def put(
    recipe_id: uuid.UUID,
    body: SaveIn,
    user: CurrentUser,
    session: Session,
    # Someone else's list, shared with you to change.
    owner: uuid.UUID | None = None,
) -> IsSaved:
    """Save a recipe as wanted or cooked, or change which."""
    owner_id = await _whose(session, user, owner)
    seen = await session.scalar(
        select(Recipe.id).where(Recipe.id == recipe_id, visibility.recipes_seen_by(user))
    )
    if seen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe.")
    row = await session.get(SavedRecipe, (owner_id, recipe_id))
    if row is None:
        held = await session.scalar(
            select(func.count()).select_from(SavedRecipe).where(SavedRecipe.user_id == owner_id)
        )
        if held >= MAX_SAVED:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"A list holds at most {MAX_SAVED:,} recipes: take some off first.",
            )
        row = SavedRecipe(user_id=owner_id, recipe_id=recipe_id)
        session.add(row)
    row.state = body.state
    await session.commit()
    return await one(recipe_id, user, session)


@router.delete("/{recipe_id}", status_code=204, dependencies=[SameOrigin])
async def remove(
    recipe_id: uuid.UUID,
    user: CurrentUser,
    session: Session,
    owner: uuid.UUID | None = None,
) -> Response:
    owner_id = await _whose(session, user, owner)
    await session.execute(
        delete(SavedRecipe).where(
            SavedRecipe.user_id == owner_id, SavedRecipe.recipe_id == recipe_id
        )
    )
    await session.commit()
    return Response(status_code=204)
