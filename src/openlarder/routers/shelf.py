"""Your shelf: the books you own (migrations 0062, 0063). *SCOPING.md:
"mark books you own, filter search to your shelf".*

A book goes on your shelf from its page, with the edition you have if it
has several, so a recipe's page opens at your edition's page number.
Search's "Only my shelf" (routers/search.py, shelf=true) keeps to them.
Books only: a website or a show isn't something you own a copy of.

Private, like the larder: it isn't in the edit history, the dumps or the
API's public reads. Shared the same way too (*Ray, 2026-11-11*): its owner
chooses which of their household groups see it; a group's view members see
it, its edit and admin members put books on it and take them off. Sharing
stays its owner's. Search with your shelf counts the shelves shared with
you. A book you can't see (a private one not shared with you) isn't shown
to you on anyone's shelf.
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
    Edition,
    Group,
    GroupMember,
    ShelfBook,
    ShelfGroup,
    Source,
    User,
)
from openlarder.routers.sources import BookSummary, summaries

router = APIRouter(prefix="/api/shelf", tags=["shelf"])
# More than any kitchen holds; a bound on what one person's rows can grow to.
MAX_BOOKS = 5000
# Group roles that change what's on a shelf shared with them.
EDITING_ROLES = ("edit", "admin")


class GroupRef(BaseModel):
    id: uuid.UUID
    name: str


class OtherShelf(BaseModel):
    """A shelf shared with you, and whether a book is on it."""

    owner_id: uuid.UUID
    owner_name: str | None
    editable: bool
    on_shelf: bool
    edition_id: uuid.UUID | None = None


class OnShelf(BaseModel):
    source_id: uuid.UUID
    on_shelf: bool
    # The edition you have, if you've said.
    edition_id: uuid.UUID | None = None
    # The shelves shared with you.
    others: list[OtherShelf] = []


class ShelfEntry(BookSummary):
    edition_id: uuid.UUID | None
    # The edition owned, as its year and ISBN, when it's been said.
    edition_year: int | None = None
    edition_isbn13: str | None = None
    added_at: datetime


class SharedShelf(BaseModel):
    owner_id: uuid.UUID
    owner_name: str | None
    # Whether you may change what's on it.
    editable: bool
    # The groups of yours it's shared through.
    through: list[GroupRef]
    books: list[ShelfEntry]


class Shelf(BaseModel):
    books: list[ShelfEntry]
    # The groups your shelf is shared with, and your groups to choose from.
    shared_with: list[GroupRef] = []
    groups: list[GroupRef] = []
    # Other people's shelves, shared with you.
    shared: list[SharedShelf] = []


class ShelfIn(BaseModel):
    edition_id: uuid.UUID | None = None


def _sharers(user: User):
    """Whose shelves are shared with a group this person is in."""
    return (
        select(ShelfGroup.user_id)
        .join(GroupMember, GroupMember.group_id == ShelfGroup.group_id)
        .where(GroupMember.user_id == user.id)
    )


def shelf_source_ids(user: User):
    """The books on someone's shelf, and the shelves shared with them, that
    they can see."""
    return (
        select(ShelfBook.source_id)
        .join(Source, Source.id == ShelfBook.source_id)
        .where(
            or_(ShelfBook.user_id == user.id, ShelfBook.user_id.in_(_sharers(user))),
            visibility.sources_seen_by(user),
        )
        .distinct()
    )


async def _others(session, user: User) -> dict[uuid.UUID, SharedShelf]:
    """The shelves shared with this person, by owner, without their books."""
    rows = await session.execute(
        select(ShelfGroup.user_id, User.display_name, Group.id, Group.name, GroupMember.role)
        .join(GroupMember, GroupMember.group_id == ShelfGroup.group_id)
        .join(Group, Group.id == ShelfGroup.group_id)
        .join(User, User.id == ShelfGroup.user_id)
        .where(GroupMember.user_id == user.id, ShelfGroup.user_id != user.id)
        .order_by(func.lower(User.display_name), ShelfGroup.user_id, func.lower(Group.name))
    )
    found: dict[uuid.UUID, SharedShelf] = {}
    for owner_id, owner_name, group_id, group_name, role in rows:
        shelf = found.setdefault(
            owner_id,
            SharedShelf(
                owner_id=owner_id, owner_name=owner_name, editable=False, through=[], books=[]
            ),
        )
        shelf.through.append(GroupRef(id=group_id, name=group_name))
        shelf.editable = shelf.editable or role in EDITING_ROLES
    return found


async def _books(
    session, viewer: User, owners: list[uuid.UUID]
) -> dict[uuid.UUID, list[ShelfEntry]]:
    """Each owner's shelf, as cards, of the books the viewer can see."""
    rows = (
        await session.execute(
            select(Source, ShelfBook, Edition)
            .join(ShelfBook, ShelfBook.source_id == Source.id)
            .outerjoin(Edition, Edition.id == ShelfBook.edition_id)
            .where(ShelfBook.user_id.in_(owners), visibility.sources_seen_by(viewer))
            .order_by(func.lower(Source.title), Source.id)
        )
    ).all()
    distinct = list({s.id: s for s, _, _ in rows}.values())
    cards = {c.id: c for c in await summaries(session, distinct)}
    found: dict[uuid.UUID, list[ShelfEntry]] = {}
    for source, shelved, edition in rows:
        found.setdefault(shelved.user_id, []).append(
            ShelfEntry(
                **cards[source.id].model_dump(),
                edition_id=shelved.edition_id,
                edition_year=edition.published_year if edition else None,
                edition_isbn13=edition.isbn13 if edition else None,
                added_at=shelved.created_at,
            )
        )
    return found


@router.get("", response_model=Shelf)
async def mine(user: CurrentUser, session: Session) -> Shelf:
    """Your shelf, then those shared with you."""
    others = await _others(session, user)
    books = await _books(session, user, [user.id, *others])
    for owner_id, shelf in others.items():
        shelf.books = books.get(owner_id, [])
    my_groups = (
        await session.execute(
            select(Group.id, Group.name, ShelfGroup.user_id)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .outerjoin(
                ShelfGroup, (ShelfGroup.group_id == Group.id) & (ShelfGroup.user_id == user.id)
            )
            .where(GroupMember.user_id == user.id)
            .order_by(func.lower(Group.name))
        )
    ).all()
    return Shelf(
        books=books.get(user.id, []),
        shared_with=[GroupRef(id=i, name=n) for i, n, shared in my_groups if shared],
        groups=[GroupRef(id=i, name=n) for i, n, _ in my_groups],
        shared=list(others.values()),
    )


class SharingIn(BaseModel):
    groups: list[uuid.UUID] = Field(default=[], max_length=50)


# Before /{source_id}, which would otherwise take "groups" for a book.
@router.put("/groups", response_model=Shelf, dependencies=[SameOrigin])
async def share(body: SharingIn, user: CurrentUser, session: Session) -> Shelf:
    """Choose which of your groups see your shelf; joining a group shares
    nothing by itself."""
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
        delete(ShelfGroup).where(ShelfGroup.user_id == user.id, ShelfGroup.group_id.not_in(chosen))
    )
    held = set(
        await session.scalars(select(ShelfGroup.group_id).where(ShelfGroup.user_id == user.id))
    )
    for group_id in chosen - held:
        session.add(ShelfGroup(user_id=user.id, group_id=group_id))
    await session.commit()
    return await mine(user, session)


async def _seen_book(session, user: User, source_id: uuid.UUID) -> Source:
    source = await session.scalar(
        select(Source).where(Source.id == source_id, visibility.sources_seen_by(user))
    )
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book.")
    if source.kind != "book":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Only books go on a shelf.")
    return source


async def _whose(session, user: User, owner: uuid.UUID | None) -> uuid.UUID:
    """The shelf to change: yours, or one shared with you that you may
    change. 404 for one you can't see, 403 for one you can only see."""
    if owner is None or owner == user.id:
        return user.id
    shelf = (await _others(session, user)).get(owner)
    if shelf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shelf.")
    if not shelf.editable:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can see this shelf, but not change what's on it."
        )
    return owner


@router.get("/{source_id}", response_model=OnShelf)
async def one(source_id: uuid.UUID, user: CurrentUser, session: Session) -> OnShelf:
    """Whether a book is on your shelf, and on those shared with you, and
    which edition."""
    others = await _others(session, user)
    rows = {
        row.user_id: row
        for row in await session.scalars(
            select(ShelfBook)
            .join(Source, Source.id == ShelfBook.source_id)
            .where(
                ShelfBook.source_id == source_id,
                ShelfBook.user_id.in_([user.id, *others]),
                visibility.sources_seen_by(user),
            )
        )
    }
    own = rows.get(user.id)
    return OnShelf(
        source_id=source_id,
        on_shelf=own is not None,
        edition_id=own.edition_id if own else None,
        others=[
            OtherShelf(
                owner_id=o.owner_id,
                owner_name=o.owner_name,
                editable=o.editable,
                on_shelf=o.owner_id in rows,
                edition_id=rows[o.owner_id].edition_id if o.owner_id in rows else None,
            )
            for o in others.values()
        ],
    )


@router.put("/{source_id}", response_model=OnShelf, dependencies=[SameOrigin])
async def put(
    source_id: uuid.UUID,
    body: ShelfIn,
    user: CurrentUser,
    session: Session,
    # Someone else's shelf, shared with you to change.
    owner: uuid.UUID | None = None,
) -> OnShelf:
    """Put a book on a shelf, or change which edition is owned."""
    owner_id = await _whose(session, user, owner)
    source = await _seen_book(session, user, source_id)
    if body.edition_id is not None:
        edition = await session.get(Edition, body.edition_id)
        if edition is None or edition.source_id != source.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "That edition isn't one of this book's."
            )
    row = await session.get(ShelfBook, (owner_id, source.id))
    if row is None:
        held = await session.scalar(
            select(func.count()).select_from(ShelfBook).where(ShelfBook.user_id == owner_id)
        )
        if held >= MAX_BOOKS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"A shelf holds at most {MAX_BOOKS:,} books.",
            )
        row = ShelfBook(user_id=owner_id, source_id=source.id)
        session.add(row)
    row.edition_id = body.edition_id
    await session.commit()
    return await one(source.id, user, session)


@router.delete("/{source_id}", status_code=204, dependencies=[SameOrigin])
async def remove(
    source_id: uuid.UUID,
    user: CurrentUser,
    session: Session,
    owner: uuid.UUID | None = None,
) -> Response:
    owner_id = await _whose(session, user, owner)
    await session.execute(
        delete(ShelfBook).where(ShelfBook.user_id == owner_id, ShelfBook.source_id == source_id)
    )
    await session.commit()
    return Response(status_code=204)
