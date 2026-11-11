"""Reading the edit history (history.py, migration 0040).

A record's page shows its history: a source's is everything in it, a
recipe's its lines, places and tags too, an ingredient's its names, an
author's their name and links. Moderators see the latest changes across
the catalog. Who may read what follows visibility.py: a record's history
only with the record, and the latest changes leave out family collections
and any ingredient or author the reader can't see.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, false, func, or_, select, true
from sqlalchemy.orm import aliased

from openlarder import revert, visibility
from openlarder.auth import ModeratorUser, SameOrigin, Viewer
from openlarder.db import Session
from openlarder.models import Author, Ingredient, Recipe, Revision, Source, Tag, User

router = APIRouter(tags=["history"])

# How a table's rows read, singular.
WHAT = {
    "sources": "source",
    "editions": "edition",
    "episodes": "episode",
    "issues": "issue",
    "web_pages": "web page",
    "source_credits": "credit",
    "source_tags": "tag on the source",
    "recipes": "recipe",
    "recipe_locations": "place",
    "recipe_ingredients": "ingredient line",
    "ingredient_options": "ingredient choice",
    "recipe_tags": "tag",
    "purchase_links": "buy link",
    "substitutions": "substitution",
    "authors": "author",
    "author_links": "author link",
    "ingredients": "ingredient",
    "ingredient_aliases": "ingredient name",
    "ingredient_allergens": "allergen",
    "diet_allergens": "allergen a diet avoids",
    "tags": "tag",
}
# The column that names a row, first found wins.
NAMED_BY = (
    "title",
    "name",
    "original_text",
    "label",
    "url",
    "isbn13",
    "credited_as",
    "page",
    "allergen",
)
# Not worth showing: keys, and what the database keeps for itself.
HIDDEN_FIELDS = {"id", "source_id", "recipe_id", "recipe_ingredient_id", "owner_id", "created_by"}
# Names for ids, looked up as the reader may see them.
LOOKUPS = {
    "ingredient_id": Ingredient,
    "parent_id": Ingredient,
    "from_ingredient_id": Ingredient,
    "to_ingredient_id": Ingredient,
    "author_id": Author,
    "tag_id": Tag,
    "diet_tag_id": Tag,
}
LIMIT = 200


class Field(BaseModel):
    field: str
    before: Any
    after: Any


class Entry(BaseModel):
    table: str
    what: str
    action: str
    # The row's name, as it was or is.
    name: str | None
    fields: list[Field]


class Change(BaseModel):
    id: uuid.UUID
    at: datetime
    # Their display name; None for a change made outside the site, or one
    # whose maker is withheld.
    by: str | None
    # Who made it isn't shown: it also touched a collection you can't see.
    withheld: bool = False
    via: str | None
    source_id: uuid.UUID | None
    entries: list[Entry]


def _name(changes: dict) -> str | None:
    for column in NAMED_BY:
        if column in changes:
            before, after = changes[column]
            value = after if after is not None else before
            if value is not None:
                return str(value)
    return None


async def _names(session, viewer: User | None, revisions: list[Revision]) -> dict[str, str]:
    """Names for the ids the revisions mention, of what the reader may see."""
    wanted: dict[type, set[str]] = {}
    for r in revisions:
        for column, (before, after) in r.changes.items():
            model = LOOKUPS.get(column)
            if model:
                wanted.setdefault(model, set()).update(v for v in (before, after) if v)
    names: dict[str, str] = {}
    for model, ids in wanted.items():
        query = select(model.id, model.name).where(model.id.in_([uuid.UUID(i) for i in ids]))
        if model is Ingredient:
            query = query.where(visibility.ingredients_seen_by(viewer))
        elif model is Author:
            query = query.where(visibility.authors_seen_by(viewer))
        names.update({str(i): n for i, n in (await session.execute(query)).all()})
    return names


# Tables whose rows have a name worth showing when a change doesn't carry it.
NAMED_TABLES = {
    "sources": (Source, Source.title),
    "recipes": (Recipe, Recipe.title),
    "ingredients": (Ingredient, Ingredient.name),
    "authors": (Author, Author.name),
    "tags": (Tag, Tag.name),
}


async def _current_names(session, viewer: User | None, revisions: list[Revision]) -> dict:
    """What a changed row is called now, for the reader, by (table, id)."""
    wanted: dict[str, set[uuid.UUID]] = {}
    for r in revisions:
        if r.action == "u" and r.record_id and r.table_name in NAMED_TABLES:
            wanted.setdefault(r.table_name, set()).add(r.record_id)
    found: dict[tuple[str, uuid.UUID], str] = {}
    for table, ids in wanted.items():
        model, column = NAMED_TABLES[table]
        query = select(model.id, column).where(model.id.in_(ids))
        query = query.where(
            {
                "sources": visibility.sources_seen_by(viewer),
                "recipes": visibility.recipes_seen_by(viewer),
                "ingredients": visibility.ingredients_seen_by(viewer),
                "authors": visibility.authors_seen_by(viewer),
            }.get(table, true())
        )
        found.update({(table, i): n for i, n in (await session.execute(query)).all()})
    return found


def _hidden(viewer: User | None):
    """Revisions the reader mustn't see: in a family collection they can't
    see, or of a source or recipe hidden from them (private, or waiting for
    review and not theirs), or of a recipe removed while it waited."""
    family_unseen = and_(
        Revision.family,
        or_(
            Revision.source_id.is_(None),
            Revision.source_id.not_in(visibility.seen_source_ids(viewer)),
        ),
    )
    conditions = [
        family_unseen,
        Revision.source_id.in_(visibility.hidden_source_ids(viewer)),
        Revision.recipe_id.in_(visibility.hidden_recipe_ids(viewer)),
    ]
    if viewer is None or not viewer.may_edit:
        gone = aliased(Revision)
        conditions.append(
            Revision.recipe_id.in_(
                select(gone.record_id).where(
                    gone.table_name == "recipes",
                    gone.action == "d",
                    gone.changes["review"][0].astext != "published",
                )
            )
        )
    # A revision of no recipe (the source's own rows) has recipe_id NULL, and
    # NULL IN (...) is unknown, not false, once anything is hidden: unknown
    # counts as not hidden, or "NOT hidden" would drop it too.
    return func.coalesce(or_(*conditions), false())


async def _changes(session, viewer: User | None, query) -> list[Change]:
    revisions = list(await session.scalars(query.order_by(Revision.id.desc()).limit(LIMIT)))
    names = await _names(session, viewer, revisions)
    current = await _current_names(session, viewer, revisions)
    # A change that also touched something the reader can't see (an
    # ingredient first named in someone's private recipe, or in one waiting
    # for review) is shown without who made it, which would point at it.
    touched_private = set(
        await session.scalars(
            select(Revision.change_id).where(
                Revision.change_id.in_({r.change_id for r in revisions}), _hidden(viewer)
            )
        )
    )
    who = dict(
        (
            await session.execute(
                select(User.id, User.display_name).where(
                    User.id.in_({r.user_id for r in revisions if r.user_id})
                )
            )
        ).all()
    )

    def show(column: str, value):
        if column in LOOKUPS and value:
            return names.get(value, "something you can't see")
        return value

    out: dict[uuid.UUID, Change] = {}
    # Each change's revisions, newest first, made into entries below.
    gathered: dict[uuid.UUID, list[Revision]] = {}
    for r in revisions:
        change = out.get(r.change_id)
        if change is None:
            hidden = r.change_id in touched_private
            change = out[r.change_id] = Change(
                id=r.change_id,
                at=r.at,
                by=None if hidden else who.get(r.user_id),
                via=None if hidden else r.via,
                source_id=None if hidden else r.source_id,
                withheld=hidden,
                entries=[],
            )
        gathered.setdefault(r.change_id, []).append(r)
    changes = []
    for change in out.values():
        # Oldest first within a change; a row added and then filled in by
        # the same save (its creator, its ingredient) reads as one addition.
        revisions_in = list(reversed(gathered[change.id]))
        added: dict[tuple, dict] = {}
        rows: list[tuple[Revision, dict]] = []
        for r in revisions_in:
            key = (r.table_name, r.record_id)
            if r.action == "u" and r.record_id and key in added:
                for column, (_, after) in r.changes.items():
                    added[key][column] = [None, after]
                continue
            values = dict(r.changes)
            if r.action == "i" and r.record_id:
                added[key] = values
            rows.append((r, values))
        entries = []
        for r, values in rows:
            fields = [
                Field(field=c, before=show(c, b), after=show(c, a))
                for c, (b, a) in sorted(values.items())
                if c not in HIDDEN_FIELDS
            ]
            if r.action == "u" and not fields:
                continue
            entries.append(
                Entry(
                    table=r.table_name,
                    what=WHAT.get(r.table_name, r.table_name),
                    action={"i": "added", "u": "changed", "d": "removed"}[r.action],
                    name=_name(values) or current.get((r.table_name, r.record_id)),
                    fields=fields,
                )
            )
        if entries:
            change.entries = entries
            changes.append(change)
    return changes


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"No such {what}.")


@router.get("/api/sources/{source_id}/history", response_model=list[Change])
async def source_history(source_id: uuid.UUID, session: Session, viewer: Viewer) -> list[Change]:
    source = await session.get(Source, source_id)
    if source is None or not await visibility.can_see(session, viewer, source):
        raise _not_found("source")
    return await _changes(
        session,
        viewer,
        select(Revision).where(Revision.source_id == source_id, ~_hidden(viewer)),
    )


@router.get("/api/recipes/{recipe_id}/history", response_model=list[Change])
async def recipe_history(recipe_id: uuid.UUID, session: Session, viewer: Viewer) -> list[Change]:
    seen = await session.scalar(
        select(Recipe.id).where(Recipe.id == recipe_id, visibility.recipes_seen_by(viewer))
    )
    if seen is None:
        raise _not_found("recipe")
    return await _changes(session, viewer, select(Revision).where(Revision.recipe_id == recipe_id))


@router.get("/api/ingredients/{ingredient_id}/history", response_model=list[Change])
async def ingredient_history(
    ingredient_id: uuid.UUID, session: Session, viewer: Viewer
) -> list[Change]:
    seen = await session.scalar(
        select(Ingredient.id).where(
            Ingredient.id == ingredient_id, visibility.ingredients_seen_by(viewer)
        )
    )
    if seen is None:
        raise _not_found("ingredient")
    return await _changes(
        session,
        viewer,
        select(Revision).where(
            or_(
                and_(Revision.table_name == "ingredients", Revision.record_id == ingredient_id),
                and_(
                    Revision.table_name.in_(("ingredient_aliases", "ingredient_allergens")),
                    Revision.parent_id == ingredient_id,
                ),
            )
        ),
    )


@router.get("/api/authors/{author_id}/history", response_model=list[Change])
async def author_history(author_id: uuid.UUID, session: Session, viewer: Viewer) -> list[Change]:
    seen = await session.scalar(
        select(Author.id).where(Author.id == author_id, visibility.authors_seen_by(viewer))
    )
    if seen is None:
        raise _not_found("author")
    return await _changes(
        session,
        viewer,
        select(Revision).where(
            or_(
                and_(Revision.table_name == "authors", Revision.record_id == author_id),
                and_(Revision.table_name == "author_links", Revision.parent_id == author_id),
            )
        ),
    )


@router.get("/api/changes", response_model=list[Change])
async def recent_changes(
    moderator: ModeratorUser, session: Session, by: str | None = Query(None, max_length=32)
) -> list[Change]:
    """The latest changes to the catalog, for moderators; optionally one
    person's. Family collections are left out, and ingredients and authors
    only theirs to see."""
    seen_ingredients = select(Ingredient.id).where(visibility.ingredients_seen_by(moderator))
    seen_authors = select(Author.id).where(visibility.authors_seen_by(moderator))
    shown = and_(
        Revision.family.is_(false()),
        ~_hidden(moderator),
        or_(
            Revision.table_name.not_in(
                (
                    "ingredients",
                    "ingredient_aliases",
                    "ingredient_allergens",
                    "authors",
                    "author_links",
                    "substitutions",
                )
            ),
            and_(Revision.table_name == "ingredients", Revision.record_id.in_(seen_ingredients)),
            and_(
                Revision.table_name.in_(
                    ("ingredient_aliases", "ingredient_allergens", "substitutions")
                ),
                Revision.parent_id.in_(seen_ingredients),
            ),
            and_(Revision.table_name == "authors", Revision.record_id.in_(seen_authors)),
            and_(Revision.table_name == "author_links", Revision.parent_id.in_(seen_authors)),
        ),
    )
    query = select(Revision).where(shown)
    if by:
        query = query.join(User, User.id == Revision.user_id).where(User.display_name == by)
    return await _changes(session, moderator, query)


class Reverted(BaseModel):
    # Rows put back, changed back or taken away.
    undone: int


@router.post("/api/changes/{change_id}/revert", response_model=Reverted, dependencies=[SameOrigin])
async def revert_change(
    change_id: uuid.UUID, moderator: ModeratorUser, session: Session
) -> Reverted:
    """Undo one change, as a new change (revert.py). Not one that touched
    anything the moderator can't see: a family collection's is its own."""
    hidden = await session.scalar(
        select(Revision.id).where(Revision.change_id == change_id, _hidden(moderator)).limit(1)
    )
    if hidden is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such change.")
    try:
        undone = await revert.revert(session, change_id)
    except revert.CantRevert as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    await session.commit()
    return Reverted(undone=undone)
