"""What every page shows about the site itself: a band saying this isn't
production, or a notice. *Ray, 2026-11-10: "an alert bar ... to notify
that this is a dev site ... controlled by an env variable".*

OPENLARDER_ENVIRONMENT=production shows nothing; anything else shows a line
naming it. OPENLARDER_NOTICE, when set, is shown instead, in any
environment.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from openlarder.routers.auth import Config

router = APIRouter(tags=["site"])
# How an environment's name reads in a sentence.
NAMES = {"dev": "development", "development": "development", "test": "test", "staging": "staging"}


class Site(BaseModel):
    environment: str
    production: bool
    # The line for the band above the header; None for no band.
    notice: str | None


@router.get("/api/site", response_model=Site)
async def site(settings: Config) -> Site:
    environment = settings.environment.strip().lower() or "development"
    production = environment == "production"
    notice = " ".join((settings.notice or "").split()) or None
    if notice is None and not production:
        name = NAMES.get(environment, environment)
        notice = (
            f"This is OpenLarder's {name} site, for trying things out: what's here may change or"
            " disappear without warning."
        )
    return Site(environment=environment, production=production, notice=notice)
