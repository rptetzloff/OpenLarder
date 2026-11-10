"""Proposed changes to published recipes (migration 0043). *Ray,
2026-11-10: review first; contributors' edits to published records next.*

A contributor who'd change a published recipe (a page, a line, a title)
proposes the edit, as the recipe form sends it, with why. It's checked as
a save would be, without saving. A moderator sees it beside the recipe as
it is now and applies it, which saves it as the contributor's edit through
"proposal:<id>" in the history, or declines it with a reason. If the recipe
has changed since it was proposed, applying needs saying so: it would
replace that change.

Only the proposer and moderators see a proposal. A recipe they can't see
(private, or waiting for review) has none for them.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from openlarder import history, recipes, references
from openlarder.agreement import Contributing
from openlarder.auth import CurrentUser, ModeratorUser, SameOrigin
from openlarder.db import Session
from openlarder.models import Edition, Proposal, Recipe, Revision, Source, User
from openlarder.routers.recipes import RecipeIn, _clean, _out, _recipe_or_404

router = APIRouter(tags=["proposals"])


class Version(BaseModel):
    """A recipe as it reads, for comparing two."""

    title: str
    chapter: str | None
    places: list[str]
    ingredients: list[str]


class ProposalOut(BaseModel):
    id: uuid.UUID
    recipe_id: uuid.UUID
    recipe_title: str
    source_id: uuid.UUID
    source_title: str
    by: str | None
    reason: str | None
    status: str
    note: str | None
    created_at: datetime
    # The recipe has changed since it was proposed.
    changed_since: bool
    current: Version
    proposed: Version


class ProposalIn(RecipeIn):
    reason: str | None = Field(default=None, max_length=500)


def _squash(text: str | None) -> str | None:
    return " ".join((text or "").split()) or None


async def _newest(session, recipe_id: uuid.UUID) -> int | None:
    return await session.scalar(
        select(func.max(Revision.id)).where(Revision.recipe_id == recipe_id)
    )


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


async def _versions(session, recipe: Recipe, viewer: User, body: dict) -> tuple[Version, Version]:
    now = await _out(session, recipe, viewer)
    proposed = RecipeIn.model_validate(body)
    # Both sides name editions the same way, so only a real change shows.
    labels = await _editions(
        session, [p.edition_id for p in now.pages] + [p.edition_id for p in proposed.editions]
    )
    current_places = [
        f"{labels.get(p.edition_id, 'Edition')}: page {p.page or 'not recorded'}" for p in now.pages
    ]
    if now.web_address:
        current_places.append(now.web_address)
    if now.issue:
        current_places.append(f"{now.issue.label}: page {now.issue.page or 'not recorded'}")
    if now.episode:
        current_places.append(now.episode.name)
    places = [
        f"{labels.get(p.edition_id, 'Edition')}: page {p.page or 'not recorded'}"
        for p in proposed.editions
    ]
    if proposed.web_address:
        places.append(proposed.web_address)
    if proposed.issue:
        places.append(f"{proposed.issue}: page {proposed.issue_page or 'not recorded'}")
    if proposed.episode:
        places.append(
            recipes.episode_name(
                proposed.episode.season, proposed.episode.number, proposed.episode.title
            )
        )
    return (
        Version(
            title=now.title, chapter=now.chapter, places=current_places, ingredients=now.ingredients
        ),
        Version(
            title=" ".join(proposed.title.split()),
            chapter=_squash(proposed.chapter),
            places=places,
            ingredients=[" ".join(line.split()) for line in proposed.ingredients if line.strip()],
        ),
    )


async def _out_one(session, p: Proposal, viewer: User) -> ProposalOut:
    recipe = await session.get_one(Recipe, p.recipe_id)
    source = await session.get_one(Source, recipe.source_id)
    current, proposed = await _versions(session, recipe, viewer, p.body)
    newest = await _newest(session, recipe.id)
    by = await session.scalar(select(User.display_name).where(User.id == p.proposed_by))
    return ProposalOut(
        id=p.id,
        recipe_id=recipe.id,
        recipe_title=recipe.title,
        source_id=source.id,
        source_title=source.title,
        by=by,
        reason=p.reason,
        status=p.status,
        note=p.note,
        created_at=p.created_at,
        changed_since=(newest or 0) > (p.based_on or 0),
        current=current,
        proposed=proposed,
    )


@router.post(
    "/api/recipes/{recipe_id}/proposals",
    response_model=ProposalOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SameOrigin],
)
async def propose(
    recipe_id: uuid.UUID, body: ProposalIn, user: Contributing, session: Session
) -> ProposalOut:
    """Propose a change; a second from the same person replaces their first."""
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
    row = await session.scalar(
        select(Proposal).where(
            Proposal.recipe_id == recipe.id,
            Proposal.proposed_by == user.id,
            Proposal.status == "open",
        )
    )
    if row is None:
        row = Proposal(recipe_id=recipe.id, proposed_by=user.id, body={})
        session.add(row)
    row.body = edit.model_dump(mode="json")
    row.reason = _squash(body.reason)
    row.based_on = await _newest(session, recipe.id)
    await session.commit()
    await session.refresh(row)
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
        .join(Recipe, Recipe.id == Proposal.recipe_id)
        .where(Proposal.proposed_by == user.id)
        .order_by(Proposal.created_at.desc())
        .limit(100)
    )
    return [await _out_one(session, p, user) for p in rows]


class Decision(BaseModel):
    action: Literal["apply", "decline"]
    note: str | None = Field(default=None, max_length=500)
    # Apply although the recipe has changed since, replacing that change.
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
    recipe = await _recipe_or_404(session, row.recipe_id, moderator)
    if body.action == "decline":
        note = _squash(body.note)
        if not note:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Say why, for the contributor."
            )
        row.status, row.note = "declined", note
    else:
        if not body.anyway and (await _newest(session, recipe.id) or 0) > (row.based_on or 0):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "The recipe has changed since this was proposed; applying it replaces that change.",
            )
        # The contributor's edit, applied by a moderator: theirs in the history.
        await history.acting(session, row.proposed_by)
        await history.via(session, f"proposal:{row.id}")
        try:
            await recipes.replace(session, recipe, _clean(RecipeIn.model_validate(row.body)))
        except recipes.InvalidRecipe as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        await references.relink(session, recipe.source_id)
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
