"""Proposed changes to published recipes and sources (migrations 0043,
0044). *Ray, 2026-11-10: review first; contributors' edits to published
records next; then "suggest changes to books".*

A contributor who'd change a published recipe (a page, a line, a title) or
a source's details (its title, subtitle, credits, editions) proposes the
edit, as the form sends it, with why. It's checked as a save would be,
without saving. A moderator sees what it would change and applies it,
which saves it as the contributor's edit through "proposal:<id>" in the
history, or declines it with a reason. If the record has changed since it
was proposed, applying needs saying so: it would replace that change.

Only the proposer and moderators see a proposal. A record they can't see
(private, or waiting for review) has none for them.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from openlarder import history, ingredients, lines, recipes, references, visibility
from openlarder.agreement import Contributing
from openlarder.auth import CurrentUser, ModeratorUser, SameOrigin
from openlarder.db import Session
from openlarder.models import Edition, Proposal, Recipe, Revision, Source, User
from openlarder.routers.recipes import RecipeIn, _clean, _out, _recipe_or_404
from openlarder.routers.sources import BookIn, apply_book_edit, get_book

router = APIRouter(tags=["proposals"])


class Difference(BaseModel):
    label: str
    now: str
    proposed: str


class Similar(BaseModel):
    id: uuid.UUID
    name: str


class NewIngredient(BaseModel):
    """A name in the proposed lines no ingredient has yet: applying the
    change adds it. With the ingredients named most like it, in case it's
    one of them written differently."""

    name: str
    similar: list[Similar]


class ProposalOut(BaseModel):
    id: uuid.UUID
    # recipe, or source (its own details).
    kind: Literal["recipe", "source"]
    # What it's for, and where to see it.
    title: str
    href: str
    # The recipe's source, or the source itself.
    source_id: uuid.UUID
    source_title: str
    recipe_id: uuid.UUID | None
    by: str | None
    reason: str | None
    status: str
    note: str | None
    created_at: datetime
    # The record has changed since it was proposed.
    changed_since: bool
    # Only what it would change.
    differences: list[Difference]
    # A recipe change's ingredients that would be new to the catalog.
    new_ingredients: list[NewIngredient] = []


def _squash(text: str | None) -> str | None:
    return " ".join((text or "").split()) or None


def _differences(now: dict[str, list[str]], proposed: dict[str, list[str]]) -> list[Difference]:
    return [
        Difference(
            label=label, now="; ".join(now[label]) or "none", proposed="; ".join(theirs) or "none"
        )
        for label, theirs in proposed.items()
        if now[label] != theirs
    ]


async def _editions(session, ids) -> dict[uuid.UUID, str]:
    rows = await session.execute(
        select(Edition.id, Edition.title, Edition.published_year, Edition.isbn13).where(
            Edition.id.in_(ids)
        )
    )
    return {
        i: " · ".join(str(x) for x in (t, y, isbn and f"ISBN {isbn}") if x) or "Edition"
        for i, t, y, isbn in rows
    }


# A recipe


async def _recipe_newest(session, recipe_id: uuid.UUID) -> int | None:
    return await session.scalar(
        select(func.max(Revision.id)).where(Revision.recipe_id == recipe_id)
    )


async def _recipe_differences(session, recipe: Recipe, viewer: User, body: dict):
    now = await _out(session, recipe, viewer)
    edit = RecipeIn.model_validate(body)
    labels = await _editions(
        session, [p.edition_id for p in now.pages] + [p.edition_id for p in edit.editions]
    )

    def page(label, p):
        return f"{label}: page {p or 'not recorded'}"

    places_now = [page(labels.get(p.edition_id, "Edition"), p.page) for p in now.pages]
    if now.web_address:
        places_now.append(now.web_address)
    if now.issue:
        places_now.append(page(now.issue.label, now.issue.page))
    if now.episode:
        places_now.append(now.episode.name)
    places = [page(labels.get(p.edition_id, "Edition"), p.page) for p in edit.editions]
    if edit.web_address:
        places.append(edit.web_address)
    if edit.issue:
        places.append(page(edit.issue, edit.issue_page))
    if edit.episode:
        places.append(
            recipes.episode_name(edit.episode.season, edit.episode.number, edit.episode.title)
        )
    return _differences(
        {
            "Title": [now.title],
            "Chapter": [now.chapter] if now.chapter else [],
            "Where": places_now,
            "Ingredients": now.ingredients,
        },
        {
            "Title": [" ".join(edit.title.split())],
            "Chapter": [c] if (c := _squash(edit.chapter)) else [],
            "Where": places,
            "Ingredients": [" ".join(line.split()) for line in edit.ingredients if line.strip()],
        },
    )


# A source's own details


async def _source_newest(session, source_id: uuid.UUID) -> int | None:
    """Its own rows' newest revision: itself, credits, editions."""
    return await session.scalar(
        select(func.max(Revision.id)).where(
            Revision.source_id == source_id,
            Revision.table_name.in_(("sources", "source_credits", "editions")),
        )
    )


async def _source_differences(session, source: Source, viewer: User, body: dict):
    now = await get_book(source.id, session, viewer)
    edit = BookIn.model_validate(body)
    by_id = {e.id: e for e in now.editions}

    def edition(e_id, title, publisher, year):
        isbn = by_id[e_id].isbn13 if e_id in by_id else None
        return " · ".join(str(x) for x in (isbn and f"ISBN {isbn}", title, publisher, year) if x)

    editions_now = [edition(e.id, e.title, e.publisher, e.published_year) for e in now.editions]
    changed = {e.id: e for e in edit.editions}
    editions = [
        edition(e.id, changed[e.id].title, changed[e.id].publisher, changed[e.id].published_year)
        if e.id in changed
        else edition(e.id, e.title, e.publisher, e.published_year)
        for e in now.editions
    ]
    return _differences(
        {
            "Title": [now.title],
            "Subtitle": [now.subtitle] if now.subtitle else [],
            "Credits": [f"{c.credited_as} ({c.role})" for c in now.credits],
            "Editions": editions_now,
        },
        {
            "Title": [" ".join(edit.title.split())],
            "Subtitle": [s] if (s := _squash(edit.subtitle)) else [],
            "Credits": [f"{' '.join(c.name.split())} ({c.role})" for c in edit.credits],
            "Editions": editions,
        },
    )


# Names like an unmatched one, for each; one query apiece.
MAX_NEW = 20


async def _new_ingredients(session, viewer: User, body: dict) -> list[NewIngredient]:
    """The proposed lines' ingredients that no ingredient the viewer can see
    has the name (or another name) of, as the recipe form works it out."""
    wanted: dict[str, str] = {}
    for line in RecipeIn.model_validate(body).ingredients:
        for option in lines.options(" ".join(line.split())) if line.strip() else []:
            if option.page is None and (key := ingredients.match_key(option.name)):
                wanted.setdefault(key, option.name)
    if not wanted:
        return []
    seen = visibility.ingredients_seen_by(viewer)
    known = await ingredients.known(session, set(wanted), seen)
    new = []
    for key, name in list(wanted.items())[:MAX_NEW]:
        if key in known:
            continue
        like = await ingredients.like(session, name, seen)
        new.append(NewIngredient(name=name, similar=[Similar(id=i, name=n) for i, n in like]))
    return new


async def _out_one(session, p: Proposal, viewer: User) -> ProposalOut:
    by = await session.scalar(select(User.display_name).where(User.id == p.proposed_by))
    common = {
        "id": p.id,
        "by": by,
        "reason": p.reason,
        "status": p.status,
        "note": p.note,
        "created_at": p.created_at,
    }
    if p.recipe_id is not None:
        recipe = await session.get_one(Recipe, p.recipe_id)
        source = await session.get_one(Source, recipe.source_id)
        newest = await _recipe_newest(session, recipe.id)
        return ProposalOut(
            **common,
            kind="recipe",
            title=recipe.title,
            href=f"/recipes/{recipe.id}",
            source_id=source.id,
            source_title=source.title,
            recipe_id=recipe.id,
            changed_since=(newest or 0) > (p.based_on or 0),
            differences=await _recipe_differences(session, recipe, viewer, p.body),
            new_ingredients=(
                await _new_ingredients(session, viewer, p.body) if p.status == "open" else []
            ),
        )
    source = await session.get_one(Source, p.source_id)
    newest = await _source_newest(session, source.id)
    return ProposalOut(
        **common,
        kind="source",
        title=source.title,
        href=f"/sources/{source.id}",
        source_id=source.id,
        source_title=source.title,
        recipe_id=None,
        changed_since=(newest or 0) > (p.based_on or 0),
        differences=await _source_differences(session, source, viewer, p.body),
    )


async def _save(
    session, user: User, target: dict, body: dict, reason: str | None, newest
) -> Proposal:
    """The proposer's open one for this record, replaced, or a new one."""
    row = await session.scalar(
        select(Proposal).where(
            *(getattr(Proposal, k) == v for k, v in target.items()),
            Proposal.proposed_by == user.id,
            Proposal.status == "open",
        )
    )
    if row is None:
        row = Proposal(**target, proposed_by=user.id, body={})
        session.add(row)
    row.body, row.reason, row.based_on = body, _squash(reason), newest
    await session.commit()
    await session.refresh(row)
    return row


class RecipeProposalIn(RecipeIn):
    reason: str | None = Field(default=None, max_length=500)


@router.post(
    "/api/recipes/{recipe_id}/proposals",
    response_model=ProposalOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def propose(
    recipe_id: uuid.UUID, body: RecipeProposalIn, user: Contributing, session: Session
) -> ProposalOut:
    """Propose a change to a recipe; a second from the same person replaces
    their first."""
    recipe = await _recipe_or_404(session, recipe_id, user)
    source = await session.get_one(Source, recipe.source_id)
    if source.kind == "family":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A family collection's recipes aren't proposed."
        )
    if recipe.review != "published" or user.may_edit:
        raise HTTPException(status.HTTP_409_CONFLICT, "Change it directly instead.")
    edit = RecipeIn.model_validate(body.model_dump(exclude={"reason"}))
    entry = _clean(edit)
    # Checked as saving it would be, then not saved.
    checking = await session.begin_nested()
    try:
        await recipes.replace(session, recipe, entry)
    except recipes.InvalidRecipe as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    finally:
        await checking.rollback()
    await session.refresh(recipe)
    row = await _save(
        session,
        user,
        {"recipe_id": recipe.id},
        edit.model_dump(mode="json"),
        body.reason,
        await _recipe_newest(session, recipe.id),
    )
    return await _out_one(session, row, user)


class SourceProposalIn(BookIn):
    reason: str | None = Field(default=None, max_length=500)


@router.post(
    "/api/sources/{source_id}/proposals",
    response_model=ProposalOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def propose_source(
    source_id: uuid.UUID, body: SourceProposalIn, user: Contributing, session: Session
) -> ProposalOut:
    """Propose a change to a source's details; a second from the same person
    replaces their first."""
    source = await session.get(Source, source_id)
    if source is None or not await visibility.can_see(session, user, source):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such source.")
    if source.kind == "family":
        raise HTTPException(status.HTTP_409_CONFLICT, "A family collection isn't proposed to.")
    if source.review != "published" or user.may_edit:
        raise HTTPException(status.HTTP_409_CONFLICT, "Change it directly instead.")
    edit = BookIn.model_validate(body.model_dump(exclude={"reason"}))
    checking = await session.begin_nested()
    try:
        await apply_book_edit(session, source, edit)
    finally:
        await checking.rollback()
    await session.refresh(source)
    row = await _save(
        session,
        user,
        {"source_id": source.id},
        edit.model_dump(mode="json"),
        body.reason,
        await _source_newest(session, source.id),
    )
    return await _out_one(session, row, user)


@router.get("/api/recipes/{recipe_id}/proposals", response_model=list[ProposalOut])
async def for_recipe(
    recipe_id: uuid.UUID, user: CurrentUser, session: Session
) -> list[ProposalOut]:
    """The open proposals for a recipe: a moderator's all of them, anyone
    else's their own."""
    recipe = await _recipe_or_404(session, recipe_id, user)
    query = select(Proposal).where(Proposal.recipe_id == recipe.id, Proposal.status == "open")
    if not user.may_edit:
        query = query.where(Proposal.proposed_by == user.id)
    return [
        await _out_one(session, p, user)
        for p in await session.scalars(query.order_by(Proposal.created_at))
    ]


@router.get("/api/review/proposals", response_model=list[ProposalOut])
async def open_proposals(moderator: ModeratorUser, session: Session) -> list[ProposalOut]:
    """Every open proposal, oldest first, for the review page."""
    rows = await session.scalars(
        select(Proposal).where(Proposal.status == "open").order_by(Proposal.created_at).limit(200)
    )
    return [await _out_one(session, p, moderator) for p in rows]


@router.get("/api/account/proposals", response_model=list[ProposalOut])
async def mine(user: CurrentUser, session: Session) -> list[ProposalOut]:
    """Yours, newest first: open, applied, declined (with why) or withdrawn."""
    rows = await session.scalars(
        select(Proposal)
        .where(Proposal.proposed_by == user.id)
        .order_by(Proposal.created_at.desc())
        .limit(100)
    )
    return [await _out_one(session, p, user) for p in rows]


class Decision(BaseModel):
    action: Literal["apply", "decline"]
    note: str | None = Field(default=None, max_length=500)
    # Apply although the record has changed since, replacing that change.
    anyway: bool = False


async def _open(session, proposal_id: uuid.UUID) -> Proposal:
    row = await session.get(Proposal, proposal_id, with_for_update=True)
    if row is None or row.status != "open":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such open proposal.")
    return row


@router.post("/api/proposals/{proposal_id}", response_model=ProposalOut, dependencies=[SameOrigin])
async def decide(
    proposal_id: uuid.UUID, body: Decision, moderator: ModeratorUser, session: Session
) -> ProposalOut:
    row = await _open(session, proposal_id)
    if row.recipe_id is not None:
        recipe = await _recipe_or_404(session, row.recipe_id, moderator)
        newest = await _recipe_newest(session, recipe.id)
    else:
        source = await session.get(Source, row.source_id)
        if source is None or not await visibility.can_see(session, moderator, source):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such open proposal.")
        newest = await _source_newest(session, source.id)
    if body.action == "decline":
        note = _squash(body.note)
        if not note:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Say why, for the contributor."
            )
        row.status, row.note = "declined", note
    else:
        if not body.anyway and (newest or 0) > (row.based_on or 0):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "It has changed since this was proposed; applying it replaces that change.",
            )
        # The contributor's edit, applied by a moderator: theirs in the history.
        await history.acting(session, row.proposed_by)
        await history.via(session, f"proposal:{row.id}")
        if row.recipe_id is not None:
            try:
                await recipes.replace(session, recipe, _clean(RecipeIn.model_validate(row.body)))
            except recipes.InvalidRecipe as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
            await references.relink(session, recipe.source_id)
        else:
            await apply_book_edit(session, source, BookIn.model_validate(row.body))
        await history.acting(session, moderator.id)
        await history.via(session, None)
        row.status = "applied"
    row.decided_by, row.decided_at = moderator.id, func.now()
    await session.commit()
    await session.refresh(row)
    return await _out_one(session, row, moderator)


@router.delete("/api/proposals/{proposal_id}", status_code=204, dependencies=[SameOrigin])
async def withdraw(proposal_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    row = await _open(session, proposal_id)
    if row.proposed_by != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such open proposal.")
    row.status = "withdrawn"
    await session.commit()
