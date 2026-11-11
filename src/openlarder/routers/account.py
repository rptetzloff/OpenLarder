"""The signed-in person's own account: their display name, their shops,
and their API keys."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from openlarder import buying, grocery, names, ratelimit
from openlarder.auth import CurrentUser, SameOrigin, hash_token, new_token
from openlarder.db import Session
from openlarder.models import ApiKey
from openlarder.ratelimit import KEY_PREFIX
from openlarder.routers.auth import Config, Me, me_for

router = APIRouter(prefix="/api/account", tags=["account"])


class DisplayName(BaseModel):
    display_name: str


@router.put("/display-name", response_model=Me, dependencies=[SameOrigin])
async def set_display_name(
    body: DisplayName, user: CurrentUser, session: Session, settings: Config
) -> Me:
    try:
        chosen = names.validate(body.display_name)
    except names.InvalidName as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    user.display_name = chosen
    user.suggested_name = None
    try:
        # Uniqueness is the database's to decide, so two people choosing the
        # same name at once cannot both get it.
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That name is taken.") from None
    await session.commit()
    return me_for(user, settings)


class Shops(BaseModel):
    # Shop keys (buying.RETAILERS), the preferred first.
    order: list[str] = Field(default=[], max_length=50)
    hidden: list[str] = Field(default=[], max_length=50)


@router.put("/shops", response_model=Me, dependencies=[SameOrigin])
async def set_shops(body: Shops, user: CurrentUser, session: Session, settings: Config) -> Me:
    """The order of the buy-link shops, and which to hide. One must be left:
    every shop can't be hidden. *Ray, 2026-11-09.*"""
    order = list(dict.fromkeys(body.order))
    hidden = list(dict.fromkeys(body.hidden))
    if unknown := [k for k in order + hidden if k not in buying.BY_KEY]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No such shop: {unknown[0]}.")
    if len(hidden) >= len(buying.RETAILERS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Leave at least one shop showing."
        )
    # The grocer chosen (set_grocer) stays.
    grocer = (user.shop_preferences or {}).get("grocer")
    user.shop_preferences = {"order": order, "hidden": hidden} | (
        {"grocer": grocer} if grocer else {}
    )
    await session.commit()
    return me_for(user, settings)


class GrocerIn(BaseModel):
    # A grocer's key (grocery.GROCERS); None, the first offered.
    grocer: str | None = None


@router.put("/grocer", response_model=Me, dependencies=[SameOrigin])
async def set_grocer(body: GrocerIn, user: CurrentUser, session: Session, settings: Config) -> Me:
    """Which grocer ingredients' links go to: Instacart unless another is
    chosen, as it may have nothing near them. *Ray, 2026-11-11.*"""
    if body.grocer is not None and body.grocer not in grocery.BY_KEY:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"No such grocer: {body.grocer}."
        )
    prefs = {k: v for k, v in (user.shop_preferences or {}).items() if k != "grocer"}
    if body.grocer:
        prefs["grocer"] = body.grocer
    user.shop_preferences = prefs or None
    await session.commit()
    return me_for(user, settings)


# API keys (ratelimit.py): made, listed and revoked by their owner.

MAX_KEYS = 5


class KeyIn(BaseModel):
    name: str = Field(max_length=60)


class KeyOut(BaseModel):
    id: uuid.UUID
    name: str
    # The key's start, to tell keys apart; the key itself is shown once.
    prefix: str
    created_at: datetime
    last_used_at: datetime | None


class KeyMade(KeyOut):
    # The key, shown this once: only its hash is kept.
    key: str


def _key_out(k: ApiKey) -> KeyOut:
    return KeyOut(
        id=k.id, name=k.name, prefix=k.prefix, created_at=k.created_at, last_used_at=k.last_used_at
    )


@router.get("/keys", response_model=list[KeyOut])
async def list_keys(user: CurrentUser, session: Session) -> list[KeyOut]:
    keys = await session.scalars(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at)
    )
    return [_key_out(k) for k in keys]


@router.post(
    "/keys", response_model=KeyMade, status_code=status.HTTP_201_CREATED, dependencies=[SameOrigin]
)
async def make_key(body: KeyIn, user: CurrentUser, session: Session) -> KeyMade:
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the key a name.")
    held = await session.scalar(
        select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user.id)
    )
    if (held or 0) >= MAX_KEYS:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{MAX_KEYS} keys at most: revoke one you don't use."
        )
    token = KEY_PREFIX + new_token()
    key = ApiKey(user_id=user.id, name=name, prefix=token[:10], token_hash=hash_token(token))
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return KeyMade(**_key_out(key).model_dump(), key=token)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SameOrigin])
async def revoke_key(key_id: uuid.UUID, user: CurrentUser, session: Session) -> Response:
    """Revoked is deleted: it stops working at once."""
    key = await session.get(ApiKey, key_id)
    if key is None or key.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such key.")
    await session.delete(key)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class Limits(BaseModel):
    reads_per_minute: int
    searches_per_minute: int
    requests_per_day: int


class LimitsOut(BaseModel):
    without_key: Limits
    with_key: Limits


@router.get("/api-limits", response_model=LimitsOut)
async def api_limits(settings: Config) -> LimitsOut:
    """The API's limits as set, for the keys panel to say."""

    def named(keyed: bool) -> Limits:
        reads, searches, per_day = ratelimit.limits(settings, keyed=keyed)
        return Limits(
            reads_per_minute=reads, searches_per_minute=searches, requests_per_day=per_day
        )

    return LimitsOut(without_key=named(False), with_key=named(True))
