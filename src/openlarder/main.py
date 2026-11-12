"""The FastAPI application.

The JSON API lives under /api; in the container the built SPA is served from
everything else, with unknown paths falling back to index.html so client-side
routes survive a reload.
"""

import asyncio
import html
import logging
import mimetypes
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from openlarder import (
    __version__,
    analytics,
    crawlers,
    dumps,
    history,
    pages,
    ratelimit,
    usage,
)
from openlarder.auth import SIGN_IN_COOKIE
from openlarder.config import Settings, get_settings
from openlarder.db import Session, dispose_engine, session_factory
from openlarder.ratelimit import rate_limit
from openlarder.routers import (
    account,
    allergens,
    auth,
    authors,
    book_requests,
    covers,
    flags,
    foods,
    go,
    groups,
    health,
    imports,
    ingredients,
    larder,
    merges,
    monitoring,
    notes,
    people,
    proposals,
    ratings,
    recipes,
    reports,
    review,
    saved,
    search,
    shelf,
    site,
    sitemaps,
    sources,
    substitutions,
    suggestions,
    tags,
    web_pages,
)
from openlarder.routers import (
    dumps as dumps_routes,
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
    # The day's rate-limit counts, so a deploy doesn't reset the daily cap.
    try:
        async with session_factory()() as session:
            await ratelimit.resume(session)
    except Exception:
        logging.getLogger(__name__).exception("Picking up today's API counts failed")
    # Search engines' crawler addresses, which the rate limit leaves alone.
    try:
        await asyncio.wait_for(crawlers.refresh(), 20)
    except Exception:
        logging.getLogger(__name__).exception("Fetching crawlers' address ranges failed")
    # API usage is written a minute at a time, and once more at shutdown.
    writer = asyncio.create_task(usage.keep_writing(session_factory()))
    # The weekly ODbL data dump, when it's set up (dumps.py).
    weekly = asyncio.create_task(dumps.keep_weekly(session_factory()))
    yield
    writer.cancel()
    weekly.cancel()
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

**Want all of it?** Take the weekly data dump instead of paging through the
API: the whole public catalog as CSV or JSON Lines, at openlarder.com/data
(and `/api/dumps`).
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


class NoIndexApi:
    """API answers and buy-link redirects aren't pages: a search engine may
    fetch them (Google renders pages with the API's data, so robots.txt
    mustn't block /api), but shouldn't list them. *Ray, 2026-11-10.*"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(("/api/", "/go/")):
            await self.app(scope, receive, send)
            return

        async def tagged(message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] = [*message["headers"], (b"x-robots-tag", b"noindex")]
            await send(message)

        await self.app(scope, receive, tagged)


app.add_middleware(NoIndexApi)
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
app.include_router(allergens.router)
app.include_router(sources.router)
app.include_router(authors.router)
app.include_router(book_requests.router)
app.include_router(recipes.router)
app.include_router(imports.router)
app.include_router(covers.router)
app.include_router(dumps_routes.router)
app.include_router(flags.router)
app.include_router(go.router)
app.include_router(groups.router)
app.include_router(history_routes.router)
app.include_router(ingredients.router)
app.include_router(larder.router)
app.include_router(monitoring.router)
app.include_router(notes.router)
app.include_router(people.router)
app.include_router(proposals.router)
app.include_router(foods.router)
app.include_router(merges.router)
app.include_router(reports.router)
app.include_router(review.router)
app.include_router(ratings.router)
app.include_router(saved.router)
app.include_router(search.router)
app.include_router(shelf.router)
app.include_router(site.router)
app.include_router(sitemaps.router)
app.include_router(substitutions.router)
app.include_router(suggestions.router)
app.include_router(tags.router)
app.include_router(web_pages.router)


# Tags whose checker reads value, as its own snippet has it, and nothing
# else: Impact's (Barnes & Noble's affiliate programme), which failed with
# content beside it. *Ray, 2026-11-10.*
VALUE_ONLY = {"impact-site-verification"}


def meta_tags(tags: dict[str, str]) -> str:
    """OPENLARDER_META_TAGS as <meta> tags: the standard content attribute
    (Google, Bing), or value alone for those in VALUE_ONLY."""
    out = []
    for name, value in tags.items():
        attribute = "value" if name.lower() in VALUE_ONLY else "content"
        out.append(f'<meta name="{html.escape(name)}" {attribute}="{html.escape(value)}" />')
    return "".join(out)


# index.html is never reused without asking: see spa_response.
RECHECK = {"Cache-Control": "no-cache"}


def spa_response(
    web_dir: Path,
    path: str,
    tags: dict[str, str] | None = None,
    head_end: str = "",
    robots: str | None = None,
) -> FileResponse | HTMLResponse:
    """A file from the built SPA, or its index.html for any other path, with
    the configured <meta> tags in its head, where a site checker reading
    the raw page finds them, and what the page says to crawlers (robots).

    index.html is sent with no-cache: it names the build's hashed scripts, and
    a browser that reused an old copy would ask for scripts a new deploy has
    removed and show a blank page, which happened on 2026-11-07. The hashed
    files under /assets are kept a year (Assets), since a new build never
    reuses their names.
    """
    candidate = (web_dir / path).resolve()
    if path and candidate.is_file() and web_dir.resolve() in candidate.parents:
        if candidate.name != "index.html":
            return FileResponse(candidate)
    if not tags and not head_end and not robots:
        return FileResponse(web_dir / "index.html", headers=RECHECK)
    page = (web_dir / "index.html").read_text(encoding="utf-8")
    if robots:
        page = pages.fill(page, pages.Page(robots=robots), "")
    return HTMLResponse(dressed(page, tags, head_end), headers=RECHECK)


def dressed(page: str, tags: dict[str, str] | None, head_end: str) -> str:
    """index.html with the configured <meta> tags and the analytics loader."""
    if tags:
        # First in the head, before every other tag: Impact's check looks
        # for its tag there and fails it anywhere else.
        page = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + meta_tags(tags), page, count=1)
    if head_end:
        # Last in the head: the analytics loader (analytics.py).
        page = page.replace("</head>", head_end + "</head>", 1)
    return page


# A Vite build's name for a file: its name, a hash of its content, its type
# ("index-tpFCub3m.js").
HASHED = re.compile(r"-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+$")
# A year, and never re-checked: the name changes when the content does.
KEEP = "public, max-age=31536000, immutable"


class Assets(StaticFiles):
    """The build's hashed files: kept a year, and their 404 never kept.

    During a deploy the old and new servers answer side by side, so a page
    from the new one can ask the old one for a file it doesn't have yet.
    Sent without Cache-Control, that 404 was given Cloudflare's four-hour
    browser default, and the site stayed unstyled for whoever got it, on
    2026-11-08. no-store makes the next load ask again.

    A file a server has is kept a year, immutable, but only under a hashed
    name: that name always means the same content, whichever server sends
    it, so no server can mark a file wrongly. Cloudflare respects the
    app's headers (Browser Cache TTL, set by Ray on 2026-11-10).
    """

    async def get_response(self, path: str, scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            raise StarletteHTTPException(404, headers={"Cache-Control": "no-store"}) from None
        if response.status_code in (200, 304) and HASHED.search(path):
            response.headers["Cache-Control"] = KEEP
        return response


def built_shell() -> str | None:
    """The built SPA's index.html, or None where there's no build (a
    development server; tests give the source's)."""
    index = WEB_DIR / "index.html"
    return index.read_text(encoding="utf-8") if index.is_file() else None


Shell = Annotated[str | None, Depends(built_shell)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def page_response(page: pages.Page, shell: str | None, settings: Settings, request: Request):
    """index.html with a page's own head (pages.py), its status, or the
    redirect to where it went."""
    if shell is None:
        raise StarletteHTTPException(404)
    if page.moved_to:
        return RedirectResponse(page.moved_to, status_code=301)
    site = settings.public_url or str(request.base_url)
    filled = pages.fill(shell, page, site)
    return HTMLResponse(
        dressed(filled, settings.meta_tags, analytics.loader(settings)),
        status_code=page.status,
        headers=RECHECK,
    )


# The pages the server knows something of before the browser draws them.
# The uuid in the path keeps these to a record's own page: /recipes/<id>/edit
# and the rest fall through to the SPA below, as before.
@app.get("/recipes/{recipe_id:uuid}", include_in_schema=False)
async def recipe_page(
    recipe_id: uuid.UUID, request: Request, session: Session, shell: Shell, settings: SettingsDep
) -> Response:
    return page_response(await pages.recipe(session, recipe_id), shell, settings, request)


@app.get("/sources/{source_id:uuid}", include_in_schema=False)
async def source_page(
    source_id: uuid.UUID, request: Request, session: Session, shell: Shell, settings: SettingsDep
) -> Response:
    return page_response(await pages.source(session, source_id), shell, settings, request)


if WEB_DIR.is_dir():
    app.mount("/assets", Assets(directory=WEB_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    # Annotated Response: FastAPI can't make a response model of a union.
    async def spa(path: str) -> Response:
        settings = get_settings()
        return spa_response(
            WEB_DIR,
            path,
            settings.meta_tags,
            analytics.loader(settings),
            pages.robots_for(path),
        )
