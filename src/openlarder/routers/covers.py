"""Book covers, served from OpenLarder's own address and cached by Cloudflare.

Each cover is fetched from Open Library on a cache miss and sent back with a
year-long immutable cache header: an Open Library cover ID names one image
for good. Cloudflare caches .jpg paths by default, so after the first
visitor a cover comes from Cloudflare's edge and nobody's browser contacts
the Internet Archive. Cloudflare's cache is not permanent, so a cover it
has dropped is fetched again; storing covers ourselves (editions.cover_key)
is for when there is storage for other reasons too. *Ray, 2026-11-07.*

Only covers of editions in the catalog are served, so this cannot be used
to relay arbitrary Open Library images.
"""

import logging
from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import exists, select

from openlarder import openlibrary
from openlarder.db import Session
from openlarder.models import Edition

log = logging.getLogger(__name__)
router = APIRouter(tags=["covers"])

IMMUTABLE = "public, max-age=31536000, immutable"


def covers_transport() -> httpx2.AsyncBaseTransport | None:
    """None means the real Open Library; tests replace this with a fake."""
    return None


Transport = Annotated[httpx2.AsyncBaseTransport | None, Depends(covers_transport)]


@router.get("/covers/{cover_id}-{size}.jpg", include_in_schema=False)
async def cover(cover_id: int, size: str, session: Session, transport: Transport) -> Response:
    known = await session.scalar(select(exists().where(Edition.open_library_cover_id == cover_id)))
    if size not in openlibrary.COVER_SIZES or not known:
        # Not cached either: the book may be imported a minute from now.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No such cover.", headers={"Cache-Control": "no-store"}
        )
    try:
        image = await openlibrary.fetch_cover(cover_id, size, transport)
    except openlibrary.NotFound:
        # Open Library lost it; worth asking again another day, so not cached.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No such cover.", headers={"Cache-Control": "no-store"}
        ) from None
    except openlibrary.Unavailable as exc:
        log.warning("cover %s-%s: %s", cover_id, size, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Open Library didn't answer.",
            headers={"Cache-Control": "no-store"},
        ) from None
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": IMMUTABLE})
