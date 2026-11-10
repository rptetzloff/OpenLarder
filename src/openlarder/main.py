"""The FastAPI application.

The JSON API lives under /api; in the container the built SPA is served from
everything else, with unknown paths falling back to index.html so client-side
routes survive a reload.
"""

import asyncio
import logging
import mimetypes
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from openlarder import __version__, history, usage
from openlarder.auth import SIGN_IN_COOKIE
from openlarder.config import get_settings
from openlarder.db import dispose_engine, session_factory
from openlarder.ratelimit import rate_limit
from openlarder.routers import (
    account,
    auth,
    authors,
    book_requests,
    covers,
    flags,
    go,
    groups,
    health,
    imports,
    ingredients,
    monitoring,
    people,
    recipes,
    search,
    sources,
    substitutions,
    suggestions,
    tags,
    web_pages,
)
from openlarder.routers import (
    history as history_routes,
)

WEB_DIR = Path(__file__).parent / "web"
# The slim image has no system MIME table, so the brand's fonts and the web
# manifest would go out as application/octet-stream.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("application/manifest+json", ".webmanifest")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # API usage is written a minute at a time, and once more at shutdown.
    writer = asyncio.create_task(usage.keep_writing(session_factory()))
    yield
    writer.cancel()
    try:
        async with session_factory()() as session:
            await usage.flush(session)
    except Exception:
        logging.getLogger(__name__).exception("Writing API usage at shutdown failed")
    await dispose_engine()


def api_description() -> str:
    """The docs' opening, with the limits as set (ratelimit.py)."""
    s = get_settings()
    return f"""
The catalog's public, read-only API: sources, editions, recipes, ingredients,
authors, tags and search. The data is open under the
[ODbL](https://opendatacommons.org/licenses/odbl/1-0/): use it, and keep what
you make from it open too, saying it's from OpenLarder.

**No key is needed** to start. Without one, each address may make
{s.api_reads_per_minute} plain reads and {s.api_searches_per_minute} searches a
minute (`/api/search`, or a list searched with `q`), and
{s.api_requests_per_day:,} requests a day (UTC). **A free key** raises them to
{s.api_key_reads_per_minute}, {s.api_key_searches_per_minute} and
{s.api_key_requests_per_day:,}: make one on Your account at openlarder.com, and
send it as `Authorization: Bearer ol_...` (or `X-API-Key: ol_...`). A key reads
what someone signed out sees; writing needs a signed-in account.

Each answer says `RateLimit-Limit`, `RateLimit-Remaining` and
`RateLimit-Policy`; over a limit, the answer is 429 with `Retry-After`.
"""


app = FastAPI(
    title="OpenLarder",
    version=__version__,
    description=api_description(),
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    # Limits /api reads from outside the site (ratelimit.py).
    dependencies=[Depends(rate_limit)],
)

settings = get_settings()
# Each request's writes are one change in the edit history (history.py).
app.add_middleware(history.Middleware)
app.add_middleware(
    SessionMiddleware,
    # Without sign-in configured nothing is ever written to this cookie, so a
    # throwaway key costs nothing. With it, Settings insists on a real one.
    secret_key=settings.session_secret or secrets.token_urlsafe(32),
    session_cookie=SIGN_IN_COOKIE,
    # An hour to finish signing in, matching how long Authlib keeps the
    # state valid: creating an account at the broker can mean waiting for a
    # verification email.
    max_age=3600,
    path="/api/auth",
    same_site="lax",
    https_only=bool(settings.public_url and settings.public_url.startswith("https://")),
)

# Health checks stay at the root: probes should not depend on the API prefix.
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(sources.router)
app.include_router(authors.router)
app.include_router(book_requests.router)
app.include_router(recipes.router)
app.include_router(imports.router)
app.include_router(covers.router)
app.include_router(flags.router)
app.include_router(go.router)
app.include_router(groups.router)
app.include_router(history_routes.router)
app.include_router(ingredients.router)
app.include_router(monitoring.router)
app.include_router(people.router)
app.include_router(search.router)
app.include_router(substitutions.router)
app.include_router(suggestions.router)
app.include_router(tags.router)
app.include_router(web_pages.router)


def spa_response(web_dir: Path, path: str) -> FileResponse:
    """A file from the built SPA, or its index.html for any other path.

    index.html is sent with no-cache: it names the build's hashed scripts, and
    a browser that reused an old copy would ask for scripts a new deploy has
    removed and show a blank page, which happened on 2026-11-07. The hashed
    files under /assets keep ordinary caching, since a new build never reuses
    their names.
    """
    candidate = (web_dir / path).resolve()
    if path and candidate.is_file() and web_dir.resolve() in candidate.parents:
        if candidate.name != "index.html":
            return FileResponse(candidate)
    return FileResponse(web_dir / "index.html", headers={"Cache-Control": "no-cache"})


class Assets(StaticFiles):
    """The build's hashed files, whose 404 must not be cached.

    During a deploy the old and new servers answer side by side, so a page
    from the new one can ask the old one for a file it doesn't have yet.
    Sent without Cache-Control, that 404 was given Cloudflare's four-hour
    browser default, and the site stayed unstyled for whoever got it, on
    2026-11-08. no-store makes the next load ask again.
    """

    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            raise StarletteHTTPException(404, headers={"Cache-Control": "no-store"}) from None


if WEB_DIR.is_dir():
    app.mount("/assets", Assets(directory=WEB_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        return spa_response(WEB_DIR, path)
