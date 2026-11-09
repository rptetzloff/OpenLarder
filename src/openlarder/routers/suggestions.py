"""The admin queue of what local models suggest (SCOPING.md, LLM-assisted
data processing): merging two ingredients, or putting one under another.

n8n adds them; an admin accepts or dismisses each here. Accepting runs the
same merge or set-parent as doing it by hand on the ingredient's page, so
its checks apply. A suggestion naming an ingredient the admin can't see is
left out, as everywhere else: n8n read public data, but an ingredient can
come to be used only by a private collection since. One naming an
ingredient that has gone (merged or deleted since) can only be dismissed.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Float, case, func, select

from openlarder import ingredients, visibility
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import Ingredient, IngredientOption, Suggestion, User

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])
PAGE = 50
# What accepting can do; line fixes wait for Workflow 3 and a page of their own.
ACTIONABLE = {"merge", "parent"}


class Side(BaseModel):
    id: uuid.UUID | None
    # The name now, or the model's if the ingredient has gone.
    name: str
    recipes: int
    exists: bool


class SuggestionOut(BaseModel):
    id: uuid.UUID
    kind: str
    # merge: "same"; parent: "a_under_b" or "b_under_a".
    decision: str | None
    # merge: which name the model would keep.
    keep: Literal["a", "b"] | None
    a: Side | None
    b: Side | None
    reason: str | None
    similarity: float | None
    # merge-v2 on: the model's word for how sure it is. A 12B model asked
    # for a number said 1 to nearly everything (merge-v1), so that's kept
    # but not shown.
    certainty: Literal["certain", "likely"] | None
    confidence: float | None
    model: str
    prompt_version: str
    status: str
    created_at: datetime
    decided_at: datetime | None
    # False when an ingredient has gone, or for a kind this page can't act on.
    actionable: bool


class SuggestionPage(BaseModel):
    suggestions: list[SuggestionOut]
    open_by_kind: dict[str, int]
    total: int


class Accept(BaseModel):
    # merge only: the name to keep, if not the model's.
    keep: Literal["a", "b"] | None = None


def _ids(row: Suggestion) -> tuple[uuid.UUID, uuid.UUID] | None:
    """The two ingredients, from the proposal (which says which is a and
    which b); None if it doesn't name two."""
    p = row.proposal if isinstance(row.proposal, dict) else {}
    try:
        return uuid.UUID(str(p["a_id"])), uuid.UUID(str(p["b_id"]))
    except (KeyError, ValueError):
        return None


def _similarity():
    # n8n writes it as a string ("0.9888"); anything else sorts last.
    raw = Suggestion.proposal["similarity"].astext
    return case((raw.regexp_match(r"^[0-9]*\.?[0-9]+$"), func.cast(raw, Float)), else_=None)


def _certainty_rank():
    # Certain first, then likely, then those that don't say (merge-v1).
    return case(
        (Suggestion.proposal["certainty"].astext == "certain", 0),
        (Suggestion.proposal["certainty"].astext == "likely", 1),
        else_=2,
    )


def _hidden_ingredient_ids(viewer: User):
    """Ingredients that exist but this admin can't see."""
    return select(Ingredient.id).where(~visibility.ingredients_seen_by(viewer))


async def _visible(session, viewer: User, rows: list[Suggestion]) -> list[Suggestion]:
    named = {i for r in rows if (ids := _ids(r)) for i in ids}
    if not named:
        return rows
    hidden = set(
        await session.scalars(_hidden_ingredient_ids(viewer).where(Ingredient.id.in_(named)))
    )
    return [r for r in rows if not ((ids := _ids(r)) and hidden & set(ids))]


async def _out(session, viewer: User, rows: list[Suggestion]) -> list[SuggestionOut]:
    named = {i for r in rows if (ids := _ids(r)) for i in ids}
    names = dict(
        (
            await session.execute(
                select(Ingredient.id, Ingredient.name).where(Ingredient.id.in_(named))
            )
        ).all()
    )
    uses = dict(
        (
            await session.execute(
                select(
                    IngredientOption.ingredient_id,
                    func.count(func.distinct(IngredientOption.recipe_id)),
                )
                .where(
                    IngredientOption.ingredient_id.in_(named),
                    visibility.options_seen_by(viewer),
                )
                .group_by(IngredientOption.ingredient_id)
            )
        ).all()
    )
    out = []
    for r in rows:
        p = r.proposal if isinstance(r.proposal, dict) else {}
        ids = _ids(r)
        sides = []
        for i, key in zip(ids or (), ("a_name", "b_name"), strict=False):
            sides.append(
                Side(
                    id=i,
                    name=names.get(i) or str(p.get(key) or "(unnamed)"),
                    recipes=uses.get(i, 0),
                    exists=i in names,
                )
            )
        a, b = (sides + [None, None])[:2]
        try:
            similarity = float(p["similarity"])
        except (KeyError, TypeError, ValueError):
            similarity = None
        keep = p.get("keep_name")
        certainty = p.get("certainty")
        out.append(
            SuggestionOut(
                id=r.id,
                kind=r.kind,
                decision=p.get("decision"),
                keep=keep if keep in ("a", "b") else None,
                a=a,
                b=b,
                reason=r.reason,
                similarity=similarity,
                certainty=certainty if certainty in ("certain", "likely") else None,
                confidence=r.confidence,
                model=r.model,
                prompt_version=r.prompt_version,
                status=r.status,
                created_at=r.created_at,
                decided_at=r.decided_at,
                actionable=r.kind in ACTIONABLE
                and a is not None
                and b is not None
                and a.exists
                and b.exists,
            )
        )
    return out


@router.get("", response_model=SuggestionPage)
async def list_suggestions(
    admin: AdminUser,
    session: Session,
    state: Literal["open", "decided"] = "open",
    kind: Literal["merge", "parent", "line_fix"] | None = None,
    offset: int = Query(0, ge=0),
) -> SuggestionPage:
    # The queue is small (hundreds), and which an admin may see depends on
    # ids inside JSON, so it's filtered here rather than in SQL.
    query = select(Suggestion).where(
        Suggestion.status == "open" if state == "open" else Suggestion.status != "open"
    )
    rows = list(
        await session.scalars(
            query.order_by(
                *(
                    (
                        _certainty_rank(),
                        _similarity().desc().nulls_last(),
                        Suggestion.created_at,
                    )
                    if state == "open"
                    else (Suggestion.decided_at.desc(),)
                )
            )
        )
    )
    rows = await _visible(session, admin, rows)
    open_rows = (
        rows
        if state == "open"
        else await _visible(
            session,
            admin,
            list(await session.scalars(select(Suggestion).where(Suggestion.status == "open"))),
        )
    )
    open_by_kind: dict[str, int] = {}
    for r in open_rows:
        open_by_kind[r.kind] = open_by_kind.get(r.kind, 0) + 1
    if kind is not None:
        rows = [r for r in rows if r.kind == kind]
    return SuggestionPage(
        suggestions=await _out(session, admin, rows[offset : offset + PAGE]),
        open_by_kind=open_by_kind,
        total=len(rows),
    )


async def _open_or_404(session, admin: User, suggestion_id: uuid.UUID) -> Suggestion:
    row = await session.get(Suggestion, suggestion_id, with_for_update=True)
    if row is None or not await _visible(session, admin, [row]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such suggestion.")
    if row.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "That suggestion has already been decided.")
    return row


async def _decide(session, admin: User, row: Suggestion, outcome: str) -> SuggestionOut:
    row.status = outcome
    row.decided_by = admin.id
    row.decided_at = func.now()
    await session.commit()
    await session.refresh(row)
    return (await _out(session, admin, [row]))[0]


@router.post("/{suggestion_id}/accept", response_model=SuggestionOut, dependencies=[SameOrigin])
async def accept(
    suggestion_id: uuid.UUID, body: Accept, admin: AdminUser, session: Session
) -> SuggestionOut:
    row = await _open_or_404(session, admin, suggestion_id)
    ids = _ids(row)
    found = [await session.get(Ingredient, i) for i in ids] if ids else []
    if row.kind not in ACTIONABLE or len(found) != 2 or None in found:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This can't be accepted here: an ingredient it names has gone. Dismiss it.",
        )
    a, b = found
    decision = row.proposal.get("decision")
    try:
        if row.kind == "merge":
            keep = body.keep or row.proposal.get("keep_name")
            if keep not in ("a", "b"):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "Say which name to keep."
                )
            kept, dropped = (a, b) if keep == "a" else (b, a)
            await ingredients.merge(session, dropped, kept)
        elif decision in ("a_under_b", "b_under_a"):
            child, parent = (a, b) if decision == "a_under_b" else (b, a)
            await ingredients.set_parent(session, child, parent)
        else:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "This suggestion doesn't say which goes under which."
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return await _decide(session, admin, row, "accepted")


@router.post("/{suggestion_id}/dismiss", response_model=SuggestionOut, dependencies=[SameOrigin])
async def dismiss(suggestion_id: uuid.UUID, admin: AdminUser, session: Session) -> SuggestionOut:
    row = await _open_or_404(session, admin, suggestion_id)
    return await _decide(session, admin, row, "dismissed")
