"""The sitemap: every page that's everyone's, for search engines to find.

Pages link to each other only once the browser has drawn them, so a
crawler had nowhere to start but the front page. /sitemap.xml is an index
of files, /sitemaps/<kind>-<n>.xml, each listing at most 50,000 addresses
(the protocol's limit) with the day each record last changed. robots.txt
points at the index. *Ray's spec, 2026-11-11.*

Only what someone signed out can see is listed (visibility.py): a private
family collection's address, or one waiting for review, is never in it.
An address is only an id, but a list of them would still say what exists.
"""

import math
from datetime import UTC, datetime
from typing import Annotated
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select

from openlarder import visibility
from openlarder.config import Settings, get_settings
from openlarder.db import Session
from openlarder.models import Author, Ingredient, Recipe, Source

router = APIRouter(tags=["sitemap"])

# The sitemap protocol's limit for one file.
PER_FILE = 50_000
# A crawler asks rarely; an hour's reuse spares the database a long list.
# Said outright: without it Cloudflare picks its own time (2026-11-08).
REUSE = {"Cache-Control": "public, max-age=3600"}
NAMESPACE = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def _kinds():
    """Each kind of page: its model, and what of it anyone can see. The
    name is the first part of its pages' addresses, too."""
    return {
        "recipes": (Recipe, visibility.recipes_seen_by(None)),
        "sources": (Source, visibility.sources_seen_by(None)),
        "ingredients": (Ingredient, visibility.ingredients_seen_by(None)),
        "authors": (Author, visibility.authors_seen_by(None)),
    }


def _site(settings: Settings, request: Request) -> str:
    return (settings.public_url or str(request.base_url)).rstrip("/")


def _xml(body: str) -> Response:
    return Response(
        f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n',
        media_type="application/xml",
        headers=REUSE,
    )


SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_index(request: Request, session: Session, settings: SettingsDep) -> Response:
    """The files there are: as many of each kind as its records fill."""
    site = _site(settings, request)
    files = []
    for kind, (model, seen) in _kinds().items():
        count = await session.scalar(select(func.count()).select_from(model).where(seen))
        for n in range(1, math.ceil((count or 0) / PER_FILE) + 1):
            files.append(
                f"<sitemap><loc>{escape(f'{site}/sitemaps/{kind}-{n}.xml')}</loc></sitemap>"
            )
    return _xml(f"<sitemapindex {NAMESPACE}>{''.join(files)}</sitemapindex>")


def _day(changed: datetime) -> str:
    """The day, in UTC."""
    return changed.astimezone(UTC).date().isoformat()


@router.get("/sitemaps/{kind}-{n:int}.xml", include_in_schema=False)
async def sitemap_file(
    kind: str, n: int, request: Request, session: Session, settings: SettingsDep
) -> Response:
    """One file of a kind's pages, in a fixed order (by id), so a record
    stays in its file as others are added around it."""
    found = _kinds().get(kind)
    if found is None or n < 1:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No such sitemap.", headers={"Cache-Control": "no-store"}
        )
    model, seen = found
    rows = (
        await session.execute(
            select(model.id, model.updated_at)
            .where(seen)
            .order_by(model.id)
            .offset((n - 1) * PER_FILE)
            .limit(PER_FILE)
        )
    ).all()
    if not rows:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No such sitemap.", headers={"Cache-Control": "no-store"}
        )
    site = _site(settings, request)
    pages = "".join(
        f"<url><loc>{escape(f'{site}/{kind}/{record}')}</loc><lastmod>{_day(changed)}</lastmod></url>"
        for record, changed in rows
    )
    return _xml(f"<urlset {NAMESPACE}>{pages}</urlset>")
