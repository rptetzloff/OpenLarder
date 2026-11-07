"""The signed-in person's own account: for now, choosing a display name."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from openlarder import names
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
