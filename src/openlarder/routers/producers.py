"""The Producers page's list (producers.py). *Ray, 2026-11-13.*"""

from fastapi import APIRouter

from openlarder import producers
from openlarder.db import Session

router = APIRouter(tags=["producers"])


@router.get("/api/producers", response_model=list[producers.ProducerOut])
async def list_producers(session: Session) -> list[producers.ProducerOut]:
    """Farms, mills and makers that sell ingredients themselves, in the
    order shown: what each supplies, where it ships, and what following its
    link earns and for whom. The same for everyone, signed in or not."""
    return await producers.listed(session)
