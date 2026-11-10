"""/go/<retailer>/<edition>: count a buy-link click, then send it on.

It records the edition, the retailer, the time and the OpenLarder page the
link was on; no user, IP address or cookie, and nothing for a bot. *Ray and
Claude, 2026-11-07 (SCOPING.md, Tracking and disclosure).* Every answer is
no-store: a cached redirect would go uncounted, and Cloudflare caches
whatever doesn't say otherwise.
"""

import uuid

from fastapi import APIRouter, Header, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from openlarder import buying
from openlarder.db import Session
from openlarder.models import Edition, PurchaseClick, Source, SourceCredit

router = APIRouter(tags=["buying"], include_in_schema=False)
NO_STORE = {"Cache-Control": "no-store"}


@router.get("/go/{retailer}/{edition_id}")
async def go(
    retailer: str,
    edition_id: uuid.UUID,
    session: Session,
    page: str | None = Query(default=None, alias="from", max_length=2000),
    user_agent: str | None = Header(default=None),
    referer: str | None = Header(default=None),
) -> RedirectResponse:
    edition = await session.get(Edition, edition_id)
    source = await session.get(Source, edition.source_id) if edition else None
    target = None
    if edition and edition.isbn13 and source and source.kind == "book":
        author = await session.scalar(
            select(SourceCredit.credited_as)
            .where(SourceCredit.source_id == source.id)
            .order_by(SourceCredit.position)
            .limit(1)
        )
        target = buying.destination(
            retailer, buying.Book(isbn13=edition.isbn13, title=source.title, author=author)
        )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such link.", headers=NO_STORE)
    if not buying.is_bot(user_agent):
        session.add(
            PurchaseClick(
                edition_id=edition_id,
                retailer=retailer,
                page=buying.page_of(page, referer),
            )
        )
        await session.commit()
    return RedirectResponse(target, status_code=status.HTTP_302_FOUND, headers=NO_STORE)
