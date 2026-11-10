"""The data dumps, for anyone, and building one now, for administrators
(dumps.py)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from openlarder import dumps, s3
from openlarder.auth import AdminUser, SameOrigin
from openlarder.db import Session
from openlarder.models import Dump
from openlarder.routers.auth import Config

router = APIRouter(tags=["data"])


class DumpOut(BaseModel):
    built_at: datetime
    csv_url: str
    csv_bytes: int
    json_url: str
    json_bytes: int
    counts: dict[str, int]


class Dumps(BaseModel):
    # Whether dumps are set up on this site.
    available: bool
    licence_url: str
    attribution: str
    latest: DumpOut | None
    older: list[DumpOut]
    # How long each is kept (OPENLARDER_DUMPS_KEEP_DAYS).
    keep_days: int


def _out(dump: Dump, settings) -> DumpOut:
    return DumpOut(
        built_at=dump.built_at,
        csv_url=dumps.public_url(settings, dump.csv_key),
        csv_bytes=dump.csv_bytes,
        json_url=dumps.public_url(settings, dump.json_key),
        json_bytes=dump.json_bytes,
        counts=dump.counts,
    )


@router.get("/api/dumps", response_model=Dumps)
async def list_dumps(session: Session, settings: Config) -> Dumps:
    """The newest dump and the eight before it: the whole public catalog,
    weekly, under the ODbL."""
    rows = (
        list(await session.scalars(select(Dump).order_by(Dump.built_at.desc()).limit(9)))
        if settings.dumps_configured
        else []
    )
    built = [_out(d, settings) for d in rows]
    return Dumps(
        available=settings.dumps_configured,
        licence_url=dumps.LICENCE_URL,
        attribution=dumps.ATTRIBUTION,
        latest=built[0] if built else None,
        older=built[1:],
        keep_days=settings.dumps_keep_days,
    )


def dumps_transport():
    """The object store's transport: the real one, unless a test swaps it."""
    return None


@router.post("/api/admin/dumps", response_model=DumpOut, dependencies=[SameOrigin])
async def build_now(
    admin: AdminUser,
    session: Session,
    settings: Config,
    transport: Annotated[object, Depends(dumps_transport)],
) -> DumpOut:
    if not settings.dumps_configured:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Dumps aren't set up: the OPENLARDER_DUMPS_ settings are."
        )
    try:
        dump = await dumps.build(session, settings, admin.id, transport=transport)
    except s3.UploadFailed as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The upload failed: {exc}") from None
    return _out(dump, settings)
