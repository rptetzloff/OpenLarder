"""FoodData Central's generic foods (fdc.py): loading them, for
administrators, and finding one to link an ingredient to, for moderators."""

import logging
import uuid
from datetime import datetime
from typing import Annotated, Literal

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select

from openlarder import fdc, fdc_match, history, visibility, wikidata
from openlarder.auth import AdminUser, ModeratorUser, SameOrigin
from openlarder.config import get_settings
from openlarder.db import Session
from openlarder.models import FdcFood, Ingredient, LinkSuggestion
from openlarder.wikidata import WikidataTransport

router = APIRouter(prefix="/api/fdc", tags=["foods"])
log = logging.getLogger(__name__)
PAGE = 100


def fdc_transport() -> httpx2.AsyncBaseTransport | None:
    """None means the real FoodData Central; tests replace this with a fake."""
    return None


Transport = Annotated[httpx2.AsyncBaseTransport | None, Depends(fdc_transport)]


class FdcStatus(BaseModel):
    foods: int
    loaded_at: datetime | None


@router.get("", response_model=FdcStatus)
async def fdc_status(admin: AdminUser, session: Session) -> FdcStatus:
    found = await fdc.status(session)
    return FdcStatus(foods=found.foods, loaded_at=found.loaded_at)


@router.post("/load", response_model=FdcStatus, dependencies=[SameOrigin])
async def load(admin: AdminUser, session: Session, transport: Transport) -> FdcStatus:
    """Download FoodData Central's generic foods and load them, again
    whenever there's a new release."""
    try:
        n = await fdc.load(session, get_settings().fdc_datasets, transport)
    except fdc.Unavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    except fdc.BadDataset as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    await session.commit()
    log.info("%s loaded %s foods from FoodData Central", admin.id, n)
    return await fdc_status(admin, session)


class FoodOut(BaseModel):
    fdc_id: int
    description: str
    data_type: str
    category: str | None
    url: str


@router.get("/foods", response_model=list[FoodOut])
async def find(
    moderator: ModeratorUser,
    session: Session,
    q: str = Query(min_length=1, max_length=200),
) -> list[FoodOut]:
    """Foods to link an ingredient to: an ID, or words in the description,
    closest first, and among those the plainest (Foundation, then SR
    Legacy, then the survey's dishes)."""
    q = " ".join(q.split())
    if q.isdigit():
        rows = await session.scalars(select(FdcFood).where(FdcFood.fdc_id == int(q)))
    else:
        # "Eggs" finds "Egg, whole": a plural's last s is left off.
        words = [_singular(w.strip(",")) for w in q.split() if w.strip(",")]
        plainest = case(
            (FdcFood.data_type == "foundation_food", 0),
            (FdcFood.data_type == "sr_legacy_food", 1),
            else_=2,
        )
        rows = await session.scalars(
            select(FdcFood)
            .where(*(FdcFood.description.ilike(f"%{_escaped(w)}%") for w in words))
            .order_by(
                func.similarity(FdcFood.description, q).desc(),
                plainest,
                func.length(FdcFood.description),
            )
            .limit(25)
        )
    return [
        FoodOut(
            fdc_id=f.fdc_id,
            description=f.description,
            data_type=f.data_type,
            category=f.category,
            url=fdc.food_url(f.fdc_id),
        )
        for f in rows
    ]


def _singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word[-1] in "sS" and word[-2] not in "sS" else word


def _escaped(word: str) -> str:
    return word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Suggested links (fdc_match.py), Admin > Ingredient links.


class Suggested(BaseModel):
    fdc: int
    wikidata: int


@router.post("/suggest", response_model=Suggested, dependencies=[SameOrigin])
async def suggest(admin: AdminUser, session: Session, transport: WikidataTransport) -> Suggested:
    """Suggest a food and a Wikidata item for each public ingredient without
    one; answers with how many new."""
    if not (await fdc.status(session)).foods:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Load FoodData Central first: there's nothing to match to."
        )
    try:
        found = await fdc_match.suggest(session, transport)
    except wikidata.Unavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Wikidata didn't answer. Try again in a minute."
        ) from None
    await session.commit()
    log.info("%s suggested %s FDC and %s Wikidata links", admin.id, found.fdc, found.wikidata)
    return Suggested(fdc=found.fdc, wikidata=found.wikidata)


class Named(BaseModel):
    id: uuid.UUID
    name: str
    recipes: int


class FoodSuggestion(BaseModel):
    id: uuid.UUID
    certainty: Literal["likely", "unsure"]
    food: FoodOut


class ItemSuggestion(BaseModel):
    id: uuid.UUID
    certainty: Literal["likely", "unsure"]
    wikidata_id: str
    label: str | None
    url: str


class LinkRow(BaseModel):
    ingredient: Named
    fdc: FoodSuggestion | None
    wikidata: ItemSuggestion | None


class LinkPage(BaseModel):
    rows: list[LinkRow]
    # Open suggestions: FDC likely and unsure, and Wikidata.
    counts: dict[str, int]
    total: int


def _food_out(f: FdcFood) -> FoodOut:
    return FoodOut(
        fdc_id=f.fdc_id,
        description=f.description,
        data_type=f.data_type,
        category=f.category,
        url=fdc.food_url(f.fdc_id),
    )


@router.get("/suggestions", response_model=LinkPage)
async def suggestions(
    moderator: ModeratorUser,
    session: Session,
    show: Literal["likely", "unsure", "wikidata"] = "likely",
    offset: int = Query(0, ge=0),
) -> LinkPage:
    """Open suggestions, an ingredient a row, the most used first: those
    with a likely food, those with an unsure one, or those with an item."""
    rows = list(
        await session.scalars(
            select(LinkSuggestion)
            .join(Ingredient, Ingredient.id == LinkSuggestion.ingredient_id)
            .where(
                LinkSuggestion.status == "open",
                visibility.ingredients_seen_by(moderator),
                # Not one linked by hand since.
                or_(
                    and_(LinkSuggestion.source == "fdc", Ingredient.fdc_id.is_(None)),
                    and_(LinkSuggestion.source == "wikidata", Ingredient.wikidata_id.is_(None)),
                ),
            )
        )
    )
    counts = {"likely": 0, "unsure": 0, "wikidata": 0}
    by_ingredient: dict[uuid.UUID, dict[str, LinkSuggestion]] = {}
    for r in rows:
        counts[r.certainty if r.source == "fdc" else "wikidata"] += 1
        by_ingredient.setdefault(r.ingredient_id, {})[r.source] = r

    def shown(found: dict[str, LinkSuggestion]) -> bool:
        if show == "wikidata":
            return "wikidata" in found
        return "fdc" in found and found["fdc"].certainty == show

    wanted = [i for i, found in by_ingredient.items() if shown(found)]
    used = await fdc_match.uses(session, wanted)
    wanted.sort(key=lambda i: -used.get(i, 0))
    page = wanted[offset : offset + PAGE]
    names = dict(
        (
            await session.execute(
                select(Ingredient.id, Ingredient.name).where(Ingredient.id.in_(page))
            )
        ).all()
    )
    wanted_foods = [s.fdc_id for i in page if (s := by_ingredient[i].get("fdc")) is not None]
    foods = {
        f.fdc_id: f
        for f in await session.scalars(select(FdcFood).where(FdcFood.fdc_id.in_(wanted_foods)))
    }
    out = []
    for i in page:
        f, w = by_ingredient[i].get("fdc"), by_ingredient[i].get("wikidata")
        out.append(
            LinkRow(
                ingredient=Named(id=i, name=names[i], recipes=used.get(i, 0)),
                fdc=(
                    FoodSuggestion(id=f.id, certainty=f.certainty, food=_food_out(foods[f.fdc_id]))
                    if f is not None
                    else None
                ),
                wikidata=(
                    ItemSuggestion(
                        id=w.id,
                        certainty=w.certainty,
                        wikidata_id=w.wikidata_id,
                        label=w.label,
                        url=wikidata.item_url(w.wikidata_id),
                    )
                    if w is not None
                    else None
                ),
            )
        )
    return LinkPage(rows=out, counts=counts, total=len(wanted))


class Decide(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=PAGE * 2)


class Decided(BaseModel):
    # Linked or dismissed; and those that couldn't be (decided already, or
    # the ingredient linked by hand since).
    done: int
    skipped: int


@router.post("/suggestions/accept", response_model=Decided, dependencies=[SameOrigin])
async def accept(body: Decide, moderator: ModeratorUser, session: Session) -> Decided:
    """Link each suggestion's ingredient to its food or item."""
    await history.via(session, "link-suggestion")
    done = 0
    for s in await _open(session, moderator, body.ids):
        ingredient = await session.get(Ingredient, s.ingredient_id)
        current = ingredient.fdc_id if s.source == "fdc" else ingredient.wikidata_id
        if current is not None:
            continue
        if s.source == "fdc":
            ingredient.fdc_id = s.fdc_id
        else:
            ingredient.wikidata_id, ingredient.wikidata_label = s.wikidata_id, s.label
        _close(s, moderator, "accepted")
        done += 1
    await session.commit()
    return Decided(done=done, skipped=len(body.ids) - done)


@router.post("/suggestions/dismiss", response_model=Decided, dependencies=[SameOrigin])
async def dismiss(body: Decide, moderator: ModeratorUser, session: Session) -> Decided:
    """Dismiss each: not suggested for that ingredient again."""
    found = await _open(session, moderator, body.ids)
    for s in found:
        _close(s, moderator, "dismissed")
    await session.commit()
    return Decided(done=len(found), skipped=len(body.ids) - len(found))


async def _open(session, moderator, ids: list[uuid.UUID]) -> list[LinkSuggestion]:
    return list(
        await session.scalars(
            select(LinkSuggestion)
            .join(Ingredient, Ingredient.id == LinkSuggestion.ingredient_id)
            .where(
                LinkSuggestion.id.in_(ids),
                LinkSuggestion.status == "open",
                visibility.ingredients_seen_by(moderator),
            )
            .with_for_update(of=LinkSuggestion)
        )
    )


def _close(s: LinkSuggestion, moderator, outcome: str) -> None:
    s.status = outcome
    s.decided_by = moderator.id
    s.decided_at = func.now()
