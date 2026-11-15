"""What every page shows about the site itself: a band saying this isn't
production, or a notice. *Ray, 2026-11-10: "an alert bar ... to notify
that this is a dev site ... controlled by an env variable".*

OPENLARDER_ENVIRONMENT=production shows nothing; anything else shows a line
naming it. OPENLARDER_NOTICE, when set, is shown instead, in any
environment.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from openlarder import producers
from openlarder.db import Session
from openlarder.routers.auth import Config

router = APIRouter(tags=["site"])
# How an environment's name reads in a sentence.
NAMES = {"dev": "development", "development": "development", "test": "test", "staging": "staging"}


class Site(BaseModel):
    environment: str
    production: bool
    # The line for the band above the header; None for no band.
    notice: str | None
    # Where page views are counted (Umami's host), for the privacy page;
    # None when they aren't.
    analytics_host: str | None = None
    # Whether an ad's click id is kept in a cookie (adclicks.py), for the
    # privacy page, which says so only where it's true.
    ad_clicks: bool = False
    # Whether any producer is listed (producers.py): the footer links their
    # page, and the privacy page and the terms speak of them, only then.
    producers: bool = False


async def _any_producers(session) -> bool:
    """Read from the shops kept in the process, so most times no query.
    Every page asks this: if the database can't be asked, the band and the
    rest are still worth sending."""
    try:
        return await producers.any_offered(session)
    except (SQLAlchemyError, OSError):
        return False


@router.get("/api/site", response_model=Site)
async def site(settings: Config, session: Session) -> Site:
    environment = settings.environment.strip().lower() or "development"
    production = environment == "production"
    notice = " ".join((settings.notice or "").split()) or None
    if notice is None and not production:
        name = NAMES.get(environment, environment)
        notice = (
            f"This is OpenLarder's {name} site, for trying things out: what's here may change or"
            " disappear without warning."
        )
    return Site(
        environment=environment,
        production=production,
        notice=notice,
        analytics_host=settings.analytics_host,
        ad_clicks=settings.ad_clicks,
        producers=await _any_producers(session),
    )
