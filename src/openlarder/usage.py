"""Counting API use by programs outside the site, for admins to watch for
abuse (Admin, API usage). *Ray, 2026-11-09: "can obfuscate or sanitize the
info, but need to id it somehow".*

ratelimit.py tells this module about each counted request; the counts are
kept in memory and written once a minute (and at shutdown), a row per
caller a day. A caller with a key is the key. One without is a pseudonym,
an HMAC of its address under the server's secret: the same every day, so a
repeat caller is seen as one, and not something the address can be got
back from without that secret. Its network goes with it (the address with
its last part dropped), to see one provider behind several. Rows go after
RETAIN_DAYS. The site's own pages aren't counted.
"""

import asyncio
import hashlib
import hmac
import ipaddress
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.config import get_settings
from openlarder.models import ApiUsage

log = logging.getLogger(__name__)
RETAIN_DAYS = 30
FLUSH_EVERY = 60.0


@dataclass
class _Count:
    key_id: uuid.UUID | None
    network: str | None
    requests: int = 0
    searches: int = 0
    refused: int = 0
    last_at: datetime | None = None


_pending: dict[tuple[date, str], _Count] = {}


def pseudonym(address: str) -> str:
    """A caller's stable name, from its address and the server's secret."""
    secret = (get_settings().session_secret or "openlarder-development").encode()
    return hmac.new(secret, address.encode(), hashlib.sha256).hexdigest()[:12]


def network(address: str) -> str | None:
    """The address's network: IPv4 to /24, IPv6 to /48."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    prefix = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def record(
    caller: str, key_id: uuid.UUID | None, address: str | None, *, search: bool, refused: bool
) -> None:
    now = datetime.now(UTC)
    count = _pending.setdefault(
        (now.date(), caller),
        _Count(key_id=key_id, network=network(address) if address else None),
    )
    if refused:
        count.refused += 1
    else:
        count.requests += 1
        count.searches += search
    count.last_at = now


def reset() -> None:
    """Forget what isn't written yet (tests)."""
    _pending.clear()


async def flush(session: AsyncSession) -> int:
    """Write what's counted since the last time, adding to the day's rows."""
    if not _pending:
        return 0
    taken = dict(_pending)
    _pending.clear()
    for (day, caller), c in taken.items():
        added = insert(ApiUsage).values(
            day=day,
            caller=caller,
            key_id=c.key_id,
            network=c.network,
            requests=c.requests,
            searches=c.searches,
            refused=c.refused,
            last_at=c.last_at,
        )
        await session.execute(
            added.on_conflict_do_update(
                index_elements=[ApiUsage.day, ApiUsage.caller],
                set_={
                    "requests": ApiUsage.requests + added.excluded.requests,
                    "searches": ApiUsage.searches + added.excluded.searches,
                    "refused": ApiUsage.refused + added.excluded.refused,
                    "last_at": added.excluded.last_at,
                },
            )
        )
    await session.commit()
    return len(taken)


async def prune(session: AsyncSession) -> None:
    oldest = datetime.now(UTC).date() - timedelta(days=RETAIN_DAYS)
    await session.execute(delete(ApiUsage).where(ApiUsage.day < oldest))
    await session.commit()


async def keep_writing(session_factory) -> None:
    """The app's background writer: flush each minute, prune each day."""
    pruned_on: date | None = None
    while True:
        await asyncio.sleep(FLUSH_EVERY)
        try:
            async with session_factory() as session:
                await flush(session)
                today = datetime.now(UTC).date()
                if pruned_on != today:
                    await prune(session)
                    pruned_on = today
        except Exception:
            # A count lost is better than a writer stopped for good.
            log.exception("Writing API usage failed")
