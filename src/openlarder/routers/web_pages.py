"""A web recipe's page, for admins: ask the Internet Archive for a copy now,
or mark the page gone so its copy is offered instead (archiving.py)."""

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from openlarder.archiving import ArchiverDep
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import WebPage

router = APIRouter(prefix="/api/web-pages", tags=["web pages"])


class Queued(BaseModel):
    # Pages the Archive will be asked for, one at a time, after this answer.
    pages: int


class GoneIn(BaseModel):
    gone: bool


async def _page_or_404(session: Session, page_id: uuid.UUID) -> WebPage:
    page = await session.get(WebPage, page_id)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such web page.")
    return page


@router.post(
    "/{page_id}/archive",
    response_model=Queued,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[SameOrigin],
)
async def archive_now(
    page_id: uuid.UUID,
    admin: AdminUser,
    session: Session,
    background: BackgroundTasks,
    archiver: ArchiverDep,
) -> Queued:
    """Ask for a copy now, as for a page whose first try failed."""
    page = await _page_or_404(session, page_id)
    background.add_task(archiver.run, [page.id])
    return Queued(pages=1)


@router.post(
    "/archive-missing",
    response_model=Queued,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[SameOrigin],
)
async def archive_missing(
    admin: AdminUser, session: Session, background: BackgroundTasks, archiver: ArchiverDep
) -> Queued:
    """Ask for every page with no copy yet, oldest first."""
    pages = list(
        await session.scalars(
            select(WebPage.id).where(WebPage.archive_url.is_(None)).order_by(WebPage.created_at)
        )
    )
    if pages:
        background.add_task(archiver.run, pages)
    return Queued(pages=len(pages))


@router.put("/{page_id}/gone", response_model=GoneIn, dependencies=[SameOrigin])
async def mark_gone(page_id: uuid.UUID, body: GoneIn, admin: AdminUser, session: Session) -> GoneIn:
    """The page no longer has the recipe (or has it again)."""
    page = await _page_or_404(session, page_id)
    page.gone = body.gone
    await session.commit()
    return GoneIn(gone=page.gone)
