"""FoodData Central's generic foods (fdc.py): loading them, for
administrators, and finding one to link an ingredient to, for moderators."""

import logging
from datetime import datetime
from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func, select

from openlarder import fdc
from openlarder.auth import AdminUser, ModeratorUser, SameOrigin
from openlarder.config import get_settings
from openlarder.db import Session
from openlarder.models import FdcFood

router = APIRouter(prefix="/api/fdc", tags=["foods"])
log = logging.getLogger(__name__)


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
