"""The signed-in person's own account: their display name, and their shops."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from openlarder import buying, names
from openlarder.auth import CurrentUser, SameOrigin
from openlarder.db import Session
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
    user.shop_preferences = {"order": order, "hidden": hidden}
    await session.commit()
    return me_for(user, settings)
