"""Asking the Internet Archive for web recipes' pages, after the response.

A capture can take a couple of minutes (archive.py), so it never holds up
saving a recipe: the route schedules it, and it runs once the answer has
gone, in a session of its own. Pages are done one at a time, so a batch
never sends the Archive more than one request at once.
"""

import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Annotated

import httpx2
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import archive, db
from openlarder.config import Settings, get_settings
from openlarder.models import RecipeLocation, WebPage

log = logging.getLogger(__name__)


class Archiver:
    def __init__(
        self,
        sessions: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        keys: tuple[str, str] | None,
        transport: httpx2.AsyncBaseTransport | None = None,
        enabled: bool = True,
    ) -> None:
        self.sessions = sessions
        self.keys = keys
        self.transport = transport
        self.enabled = enabled

    async def run(self, page_ids: list[uuid.UUID]) -> None:
        if not self.enabled:
            return
        async with self.sessions() as session:
            for page_id in page_ids:
                page = await session.get(WebPage, page_id)
                if page is None:
                    continue
                page.archive_tried_at = datetime.now(UTC)
                copy = await archive.copy_of(page.url, page.created_at, self.keys, self.transport)
                if copy:
                    page.archive_url, page.archived_at = copy.url, copy.at
                else:
                    log.info("No Internet Archive copy of %s yet", page.url)
                await session.commit()


def get_archiver(settings: Annotated[Settings, Depends(get_settings)]) -> Archiver:
    return Archiver(db.session_factory(), settings.archive_keys, enabled=settings.archive_web_pages)


ArchiverDep = Annotated[Archiver, Depends(get_archiver)]


async def uncopied(session: AsyncSession, recipe_id: uuid.UUID) -> list[uuid.UUID]:
    """The recipe's web page, if it has no copy yet."""
    return list(
        await session.scalars(
            select(WebPage.id)
            .join(RecipeLocation, RecipeLocation.web_page_id == WebPage.id)
            .where(RecipeLocation.recipe_id == recipe_id, WebPage.archive_url.is_(None))
        )
    )
