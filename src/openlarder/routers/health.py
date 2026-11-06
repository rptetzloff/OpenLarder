"""Liveness (/healthz) and readiness (/readyz).

Separate so a database blip fails readiness without making the platform
restart a process that is fine.
"""

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from openlarder import __version__
from openlarder.db import Session

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str
    version: str


class Readiness(BaseModel):
    status: str
    database: str
    revision: str | None = None


@router.get("/healthz", response_model=Health)
async def healthz() -> Health:
    return Health(status="ok", version=__version__)


@router.get("/readyz", response_model=Readiness)
async def readyz(response: Response, session: Session) -> Readiness:
    try:
        revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Readiness(status="degraded", database="unreachable")
    return Readiness(status="ok", database="reachable", revision=revision)
