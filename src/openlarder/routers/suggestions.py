"""The admin queue of what local models suggest (SCOPING.md, LLM-assisted
data processing): merging two ingredients, putting one under another, or
tagging a recipe.

n8n adds them; an admin accepts or dismisses each here. Accepting runs the
same merge or set-parent as doing it by hand on the ingredient's page, so
its checks apply. A suggestion naming an ingredient the admin can't see is
left out, as everywhere else: n8n read public data, but an ingredient can
come to be used only by a private collection since. One naming an
ingredient that has gone (merged or deleted since) can only be dismissed.
A tag suggestion is the same for its recipe: hidden if the recipe has come
to be private, dismissable only if the recipe or the tag has gone; accepting
tags the recipe, as "Edit tags" would.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Float, case, func, select

from openlarder import ingredients, visibility
from openlarder.auth import ModeratorUser, SameOrigin
from openlarder.db import Session
from openlarder.models import (
    Ingredient,
    IngredientOption,
    Recipe,
    RecipeTag,
    Source,
    SourceTag,
    Suggestion,
    Tag,
    User,
)

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])
PAGE = 50
# What accepting can do; line fixes wait for Workflow 3 and a page of their own.
ACTIONABLE = {"merge", "parent", "tag"}


class Side(BaseModel):
    id: uuid.UUID | None
    # The name now, or the model's if the ingredient has gone.
    name: str
    recipes: int
    exists: bool


class RecipeRef(BaseModel):
    id: uuid.UUID
    # Its title now, or the model's if it has gone.
    title: str
    chapter: str | None = None
    source_id: uuid.UUID | None = None
    source_title: str | None = None
    exists: bool


class TagRef(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    exists: bool
    # The recipe has it already, its own or its source's.
    already: bool = False


class SuggestionOut(BaseModel):
    id: uuid.UUID
    kind: str
    # merge: "same"; parent: "a_under_b" or "b_under_a".
    decision: str | None
    # merge: which name the model would keep.
    keep: Literal["a", "b"] | None
    a: Side | None
    b: Side | None
    # tag: the recipe, and the tag for it.
    recipe: RecipeRef | None = None
    tag: TagRef | None = None
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


def _tag_target(row: Suggestion) -> tuple[uuid.UUID, uuid.UUID] | None:
    """A tag suggestion's recipe and tag; None if it doesn't name both."""
    p = row.proposal if isinstance(row.proposal, dict) else {}
    if row.kind != "tag":
        return None
    try:
        return uuid.UUID(str(p["recipe_id"])), uuid.UUID(str(p["tag_id"]))
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
    hidden = (
        set(await session.scalars(_hidden_ingredient_ids(viewer).where(Ingredient.id.in_(named))))
        if named
        else set()
    )
    tagged = {t[0] for r in rows if (t := _tag_target(r))}
    hidden_recipes = (
        set(
            await session.scalars(
                select(Recipe.id).where(Recipe.id.in_(tagged), ~visibility.recipes_seen_by(viewer))
            )
        )
        if tagged
        else set()
    )
    return [
        r
        for r in rows
        if not ((ids := _ids(r)) and hidden & set(ids))
        and not ((t := _tag_target(r)) and t[0] in hidden_recipes)
    ]


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
    targets = {r.id: t for r in rows if (t := _tag_target(r))}
    recipes = {
        rid: (title, chapter, sid, stitle)
        for rid, title, chapter, sid, stitle in await session.execute(
            select(Recipe.id, Recipe.title, Recipe.chapter, Source.id, Source.title)
            .join(Source, Source.id == Recipe.source_id)
            .where(Recipe.id.in_([t[0] for t in targets.values()]))
        )
    }
    tags = {
        t.id: t
        for t in await session.scalars(
            select(Tag).where(Tag.id.in_([t[1] for t in targets.values()]))
        )
    }
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
        recipe_ref = tag_ref = None
        if r.id in targets:
            rid, tid = targets[r.id]
            found = recipes.get(rid)
            recipe_ref = RecipeRef(
                id=rid,
                title=found[0] if found else str(p.get("recipe_title") or "(unnamed)"),
                chapter=found[1] if found else None,
                source_id=found[2] if found else None,
                source_title=found[3] if found else None,
                exists=found is not None,
            )
            tag = tags.get(tid)
            tag_ref = TagRef(
                id=tid,
                kind=str(tag.kind) if tag else str(p.get("tag_kind") or ""),
                name=tag.name if tag else str(p.get("tag_name") or "(unnamed)"),
                exists=tag is not None,
                already=bool(found and tag and await _has_tag(session, rid, tid)),
            )
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
                recipe=recipe_ref,
                tag=tag_ref,
                actionable=r.kind in ACTIONABLE
                and (
                    bool(recipe_ref and tag_ref and recipe_ref.exists and tag_ref.exists)
                    if r.kind == "tag"
                    else (a is not None and b is not None and a.exists and b.exists)
                ),
            )
        )
    return out


@router.get("", response_model=SuggestionPage)
async def list_suggestions(
    admin: ModeratorUser,
    session: Session,
    state: Literal["open", "decided"] = "open",
    kind: Literal["merge", "parent", "line_fix", "tag"] | None = None,
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


async def _has_tag(session, recipe_id: uuid.UUID, tag_id: uuid.UUID) -> bool:
    """The recipe has the tag, its own or its source's."""
    own = select(RecipeTag).where(RecipeTag.recipe_id == recipe_id, RecipeTag.tag_id == tag_id)
    inherited = (
        select(SourceTag)
        .join(Recipe, Recipe.source_id == SourceTag.source_id)
        .where(Recipe.id == recipe_id, SourceTag.tag_id == tag_id)
    )
    return bool(
        await session.scalar(select(own.exists()))
        or await session.scalar(select(inherited.exists()))
    )


@router.post("/{suggestion_id}/accept", response_model=SuggestionOut, dependencies=[SameOrigin])
async def accept(
    suggestion_id: uuid.UUID, body: Accept, admin: ModeratorUser, session: Session
) -> SuggestionOut:
    row = await _open_or_404(session, admin, suggestion_id)
    if row.kind == "tag":
        target = _tag_target(row)
        recipe = await session.get(Recipe, target[0]) if target else None
        tag = await session.get(Tag, target[1]) if target else None
        if recipe is None or tag is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This can't be accepted: its recipe or its tag has gone. Dismiss it.",
            )
        # Already there, its own or its source's: nothing to add.
        if not await _has_tag(session, recipe.id, tag.id):
            session.add(RecipeTag(recipe_id=recipe.id, tag_id=tag.id))
        return await _decide(session, admin, row, "accepted")
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
async def dismiss(
    suggestion_id: uuid.UUID, admin: ModeratorUser, session: Session
) -> SuggestionOut:
    row = await _open_or_404(session, admin, suggestion_id)
    return await _decide(session, admin, row, "dismissed")
