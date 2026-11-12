"""Notes on recipes: your own words about one (migration 0069). *Ray,
2026-11-11: "more than reviews... notes.... that are kept personal (or
shared)".*

One note per person per recipe: what you changed, what you'd do next
time. A note is yours alone unless you tick which of your household
groups see it, as with a larder list; their members read it on the
recipe's page, and only you change it. `/api/notes` lists the notes you
can see, yours and those shared with you, for the Saved page.

Private: not in the edit history, the dumps or the API's public reads, and
no moderator or administrator role sees a note it isn't shared with. A
note on a recipe you can no longer see isn't shown to you. OpenLarder
keeps no amounts or method for a recipe; a note is the person's own, and
the form asks them not to copy the source's text into it.
"""

import uuid
from datetime import datetime

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
    RecipeNote,
    RecipeNoteGroup,
    Source,
    User,
)
from openlarder.routers.ingredients import UsedBy, with_pages

router = APIRouter(tags=["notes"])
MAX_LENGTH = 2000


class GroupRef(BaseModel):
    id: uuid.UUID
    name: str


class Mine(BaseModel):
    body: str
    # The groups it's shared with; none: only you see it.
    shared_with: list[GroupRef]
    updated_at: datetime


class Theirs(BaseModel):
    author: str | None
    body: str
    # The groups of yours it reaches you through.
    through: list[GroupRef]
    updated_at: datetime


class Notes(BaseModel):
    mine: Mine | None
    # Your groups, to share a note with.
    groups: list[GroupRef]
    # Other people's notes on this recipe, shared with you.
    others: list[Theirs]


class NoteIn(BaseModel):
    body: str = Field(max_length=MAX_LENGTH)
    groups: list[uuid.UUID] = Field(default=[], max_length=50)


class Listed(UsedBy):
    """A recipe with a note you can see."""

    body: str
    mine: bool
    author: str | None
    noted_at: datetime


class NoteList(BaseModel):
    notes: list[Listed]


def _my_groups(user: User):
    return select(GroupMember.group_id).where(GroupMember.user_id == user.id)


def _reaching(user: User):
    """The notes other people have shared with a group this person is in."""
    return select(RecipeNoteGroup.note_id).where(RecipeNoteGroup.group_id.in_(_my_groups(user)))


async def _seen(session, user: User, recipe_id: uuid.UUID) -> None:
    seen = await session.scalar(
        select(Recipe.id).where(Recipe.id == recipe_id, visibility.recipes_seen_by(user))
    )
    if seen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipe.")


async def _shared(
    session, user: User, note_ids: list[uuid.UUID], mine_too: bool
) -> dict[uuid.UUID, list[GroupRef]]:
    """Each note's groups: all of them for your own, the ones you're in
    otherwise."""
    if not note_ids:
        return {}
    query = (
        select(RecipeNoteGroup.note_id, Group.id, Group.name)
        .join(Group, Group.id == RecipeNoteGroup.group_id)
        .where(RecipeNoteGroup.note_id.in_(note_ids))
        .order_by(func.lower(Group.name))
    )
    if not mine_too:
        query = query.where(RecipeNoteGroup.group_id.in_(_my_groups(user)))
    found: dict[uuid.UUID, list[GroupRef]] = {}
    for note_id, group_id, name in await session.execute(query):
        found.setdefault(note_id, []).append(GroupRef(id=group_id, name=name))
    return found


async def _notes(session, user: User, recipe_id: uuid.UUID) -> Notes:
    own = await session.scalar(
        select(RecipeNote).where(RecipeNote.user_id == user.id, RecipeNote.recipe_id == recipe_id)
    )
    mine = None
    if own is not None:
        groups = (await _shared(session, user, [own.id], mine_too=True)).get(own.id, [])
        mine = Mine(body=own.body, shared_with=groups, updated_at=own.updated_at)
    theirs = (
        await session.execute(
            select(RecipeNote, User.display_name)
            .join(User, User.id == RecipeNote.user_id)
            .where(
                RecipeNote.recipe_id == recipe_id,
                RecipeNote.user_id != user.id,
                RecipeNote.id.in_(_reaching(user)),
            )
            .order_by(RecipeNote.updated_at.desc())
        )
    ).all()
    through = await _shared(session, user, [n.id for n, _ in theirs], mine_too=False)
    my_groups = await session.execute(
        select(Group.id, Group.name)
        .where(Group.id.in_(_my_groups(user)))
        .order_by(func.lower(Group.name))
    )
    return Notes(
        mine=mine,
        groups=[GroupRef(id=i, name=n) for i, n in my_groups],
        others=[
            Theirs(author=name, body=n.body, through=through.get(n.id, []), updated_at=n.updated_at)
            for n, name in theirs
        ],
    )


@router.get("/api/notes", response_model=NoteList)
async def all_notes(user: CurrentUser, session: Session) -> NoteList:
    """Every note you can see, yours first, on recipes you can see: newest
    first."""
    rows = (
        await session.execute(
            select(Recipe.id, Recipe.title, Source.id, Source.title, RecipeNote, User.display_name)
            .join(RecipeNote, RecipeNote.recipe_id == Recipe.id)
            .join(Source, Source.id == Recipe.source_id)
            .join(User, User.id == RecipeNote.user_id)
            .where(
                or_(RecipeNote.user_id == user.id, RecipeNote.id.in_(_reaching(user))),
                visibility.recipes_seen_by(user),
            )
            .order_by((RecipeNote.user_id != user.id), RecipeNote.updated_at.desc())
        )
    ).all()
    distinct = list({r[0]: r[:4] for r in rows}.values())
    cards = {c.id: c for c in await with_pages(session, distinct)}
    return NoteList(
        notes=[
            Listed(
                **cards[recipe_id].model_dump(),
                body=note.body,
                mine=note.user_id == user.id,
                author=None if note.user_id == user.id else name,
                noted_at=note.updated_at,
            )
            for recipe_id, _, _, _, note, name in rows
        ]
    )


@router.get("/api/recipes/{recipe_id}/notes", response_model=Notes)
async def get_notes(recipe_id: uuid.UUID, user: CurrentUser, session: Session) -> Notes:
    """Your note on a recipe, and the notes on it shared with you."""
    await _seen(session, user, recipe_id)
    return await _notes(session, user, recipe_id)


@router.put("/api/recipes/{recipe_id}/notes", response_model=Notes, dependencies=[SameOrigin])
async def put_note(
    recipe_id: uuid.UUID, body: NoteIn, user: CurrentUser, session: Session
) -> Notes:
    """Write your note on a recipe, or change it, and choose which of your
    groups see it."""
    await _seen(session, user, recipe_id)
    words = body.body.strip()
    if not words:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Write something first.")
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
    note = await session.scalar(
        select(RecipeNote).where(RecipeNote.user_id == user.id, RecipeNote.recipe_id == recipe_id)
    )
    if note is None:
        note = RecipeNote(user_id=user.id, recipe_id=recipe_id, body=words)
        session.add(note)
        await session.flush()
    else:
        note.body = words
    await session.execute(
        delete(RecipeNoteGroup).where(
            RecipeNoteGroup.note_id == note.id, RecipeNoteGroup.group_id.not_in(chosen)
        )
    )
    held = set(
        await session.scalars(
            select(RecipeNoteGroup.group_id).where(RecipeNoteGroup.note_id == note.id)
        )
    )
    for group_id in chosen - held:
        session.add(RecipeNoteGroup(note_id=note.id, group_id=group_id))
    await session.commit()
    return await _notes(session, user, recipe_id)


@router.delete("/api/recipes/{recipe_id}/notes", status_code=204, dependencies=[SameOrigin])
async def delete_note(recipe_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    await session.execute(
        delete(RecipeNote).where(RecipeNote.user_id == user.id, RecipeNote.recipe_id == recipe_id)
    )
    await session.commit()
    return Response(status_code=204)
