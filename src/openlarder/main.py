"""The FastAPI application.

The JSON API lives under /api; in the container the built SPA is served from
everything else, with unknown paths falling back to index.html so client-side
routes survive a reload.
"""

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from openlarder import __version__
from openlarder.auth import SIGN_IN_COOKIE
from openlarder.config import get_settings
from openlarder.db import dispose_engine
from openlarder.routers import (
    account,
    auth,
    authors,
    covers,
    flags,
    groups,
    health,
    imports,
    ingredients,
    recipes,
    search,
    sources,
    substitutions,
    web_pages,
)

WEB_DIR = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await dispose_engine()


app = FastAPI(
    title="OpenLarder",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

settings = get_settings()
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
app.include_router(recipes.router)
app.include_router(imports.router)
app.include_router(covers.router)
app.include_router(flags.router)
app.include_router(groups.router)
app.include_router(ingredients.router)
app.include_router(search.router)
app.include_router(substitutions.router)
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
