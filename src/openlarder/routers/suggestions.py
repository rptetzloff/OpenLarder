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
tags the recipe, as "Edit tags" would. An allergen suggestion (allergen_rules.py,
or n8n) is the same for its ingredient; accepting records the allergen on it,
as its page would, and likely ones can be accepted a page at a time.

A title suggestion (title_rules.py) names a book and the title proposed for
it. Accepting changes the title, as the moderator's edit. It's hidden when
the book can't be seen by anyone signed out (the rules only read public
books, but one can be hidden since), and can only be dismissed when the
book has gone or its title has changed since it was suggested.
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Float, case, func, select

from openlarder import (
    allergen_rules,
    allergens,
    history,
    ingredients,
    title_rules,
    visibility,
)
from openlarder.auth import AdminUser, ModeratorUser, SameOrigin
from openlarder.db import Session
from openlarder.models import (
    Ingredient,
    IngredientAllergen,
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
ACTIONABLE = {"merge", "parent", "tag", "allergen", *title_rules.KINDS}
Kind = Literal["merge", "parent", "line_fix", "tag", "allergen", "title_case", "title_apostrophe"]


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


class AllergenRef(BaseModel):
    key: str
    label: str
    # What's suggested: contains or may_contain.
    status: str
    # The ingredient records something about it already, or inherits it.
    already: bool = False
    exists: bool = True


class TitleRef(BaseModel):
    source_id: uuid.UUID
    # The title when it was suggested, and the one proposed.
    was: str
    proposed: str
    # The source is still there, and still has the title it had.
    exists: bool
    unchanged: bool


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
    # allergen: the ingredient (as a), and the allergen for it.
    allergen: AllergenRef | None = None
    # title_case, title_apostrophe: the book and the title proposed.
    title: TitleRef | None = None
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


def _allergen_target(row: Suggestion) -> tuple[uuid.UUID, str, str] | None:
    """An allergen suggestion's ingredient, allergen and status; None if it
    doesn't name them."""
    p = row.proposal if isinstance(row.proposal, dict) else {}
    if row.kind != "allergen":
        return None
    try:
        wanted = str(p["status"])
        if wanted not in ("contains", "may_contain"):
            return None
        return uuid.UUID(str(p["ingredient_id"])), str(p["allergen"]), wanted
    except (KeyError, ValueError):
        return None


def _title_target(row: Suggestion) -> tuple[uuid.UUID, str, str] | None:
    """A title suggestion's source, the title it had and the one proposed;
    None if it doesn't name them."""
    p = row.proposal if isinstance(row.proposal, dict) else {}
    if row.kind not in title_rules.KINDS:
        return None
    try:
        return uuid.UUID(str(p["source_id"])), str(p["title_now"]), str(p["title"])
    except (KeyError, ValueError):
        return None


def _named(row: Suggestion) -> list[uuid.UUID]:
    """The ingredients a suggestion names."""
    if ids := _ids(row):
        return list(ids)
    if t := _allergen_target(row):
        return [t[0]]
    return []


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
    named = {i for r in rows for i in _named(r)}
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
    titled = {t[0] for r in rows if (t := _title_target(r))}
    # Not the moderator's own view of it: a private collection is hidden
    # from moderators already, and a book waiting for review isn't one
    # the rules read. Asked as someone signed out, both stay out.
    hidden_sources = (
        set(
            await session.scalars(
                select(Source.id).where(Source.id.in_(titled), ~visibility.sources_seen_by(None))
            )
        )
        if titled
        else set()
    )
    return [
        r
        for r in rows
        if not (hidden & set(_named(r)))
        and not ((t := _tag_target(r)) and t[0] in hidden_recipes)
        and not ((s := _title_target(r)) and s[0] in hidden_sources)
    ]


async def _out(session, viewer: User, rows: list[Suggestion]) -> list[SuggestionOut]:
    named = {i for r in rows for i in _named(r)}
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
    labels = {a.key: a.label for a in await allergens.listed(session)}
    on_ingredients = {r.id: t for r in rows if (t := _allergen_target(r))}
    recorded = await allergens.recorded(
        session, list({t[0] for t in on_ingredients.values() if t[0] in names})
    )
    on_sources = {r.id: t for r in rows if (t := _title_target(r))}
    titles_now = dict(
        (
            await session.execute(
                select(Source.id, Source.title).where(
                    Source.id.in_([t[0] for t in on_sources.values()])
                )
            )
        ).all()
    )
    out = []
    for r in rows:
        p = r.proposal if isinstance(r.proposal, dict) else {}
        ids = _ids(r)
        if r.id in on_ingredients:
            ids = (on_ingredients[r.id][0],)
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
        allergen_ref = None
        if r.id in on_ingredients:
            ingredient_id, key, wanted = on_ingredients[r.id]
            if a is not None and not a.exists:
                a.name = str(p.get("ingredient_name") or a.name)
            allergen_ref = AllergenRef(
                key=key,
                label=labels.get(key, key),
                status=wanted,
                already=key in recorded.get(ingredient_id, {}),
                exists=key in labels,
            )
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
        title_ref = None
        if r.id in on_sources:
            source_id, was, proposed = on_sources[r.id]
            title_ref = TitleRef(
                source_id=source_id,
                was=was,
                proposed=proposed,
                exists=source_id in titles_now,
                unchanged=titles_now.get(source_id) == was,
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
                allergen=allergen_ref,
                title=title_ref,
                actionable=r.kind in ACTIONABLE
                and (
                    bool(title_ref and title_ref.exists and title_ref.unchanged)
                    if r.kind in title_rules.KINDS
                    else bool(recipe_ref and tag_ref and recipe_ref.exists and tag_ref.exists)
                    if r.kind == "tag"
                    else bool(a and a.exists and allergen_ref and allergen_ref.exists)
                    if r.kind == "allergen"
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
    kind: Kind | None = None,
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
    # Applied as the moderator's edit, marked with what suggested it.
    await history.via(session, f"suggestion:{row.id}")
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
    if row.kind == "allergen":
        await _record_allergen(session, row)
        return await _decide(session, admin, row, "accepted")
    if row.kind in title_rules.KINDS:
        target = _title_target(row)
        source = await session.get(Source, target[0], with_for_update=True) if target else None
        if target is None or source is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "This can't be accepted: its book has gone. Dismiss it."
            )
        if source.title != target[1]:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This can't be accepted: the title has changed since it was suggested. Dismiss it.",
            )
        source.title = target[2]
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


async def _record_allergen(session, row: Suggestion) -> None:
    """Record a suggested allergen on its ingredient, beside what it records."""
    target = _allergen_target(row)
    ingredient = await session.get(Ingredient, target[0]) if target else None
    if target is None or ingredient is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This can't be accepted: its ingredient has gone. Dismiss it.",
        )
    own = {
        a.allergen: a.status
        for a in await session.scalars(
            select(IngredientAllergen).where(IngredientAllergen.ingredient_id == ingredient.id)
        )
    }
    try:
        await allergens.record(session, ingredient, {**own, target[1]: target[2]})
    except allergens.Unknown as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{exc} Dismiss it.") from None


class Ids(BaseModel):
    ids: list[uuid.UUID]


class Done(BaseModel):
    done: int
    # Decided already, gone, hidden, or not an allergen suggestion.
    skipped: int


@router.post("/accept-allergens", response_model=Done, dependencies=[SameOrigin])
async def accept_allergens(body: Ids, admin: ModeratorUser, session: Session) -> Done:
    """Accept many allergen suggestions at once: a page of likely ones."""
    rows = list(
        await session.scalars(
            select(Suggestion)
            .where(
                Suggestion.id.in_(body.ids),
                Suggestion.kind == "allergen",
                Suggestion.status == "open",
            )
            .with_for_update()
        )
    )
    rows = await _visible(session, admin, rows)
    done = 0
    for row in rows:
        await history.via(session, f"suggestion:{row.id}")
        try:
            async with session.begin_nested():
                await _record_allergen(session, row)
        except HTTPException:
            continue
        row.status, row.decided_by, row.decided_at = "accepted", admin.id, func.now()
        done += 1
    await session.commit()
    return Done(done=done, skipped=len(set(body.ids)) - done)


class Suggested(BaseModel):
    suggested: int


@router.post("/allergens", response_model=Suggested, dependencies=[SameOrigin])
async def suggest_allergens(admin: AdminUser, session: Session) -> Suggested:
    """Suggest allergens from ingredients' names (allergen_rules.py)."""
    return Suggested(suggested=await allergen_rules.suggest(session))


@router.post("/titles", response_model=Suggested, dependencies=[SameOrigin])
async def suggest_titles(admin: AdminUser, session: Session) -> Suggested:
    """Suggest fixes to books' titles: capitals, and a lost apostrophe
    (title_rules.py)."""
    new = await title_rules.sweep(session)
    await session.commit()
    return Suggested(suggested=new)
