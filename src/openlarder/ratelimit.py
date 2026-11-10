"""Rate limits on the public API (SCOPING.md, API).

Programs may read /api without a key, at a low rate per address; a free key
(Authorization: Bearer ol_..., or X-API-Key) raises every limit about ten
times, so anyone doing real work identifies themselves and has someone to
hear from. *Ray, 2026-11-09.* Three limits apply, each a setting:

- plain reads (a book, a recipe, an ingredient): a minute's allowance;
- searches, the expensive ones (/api/search, and a list searched with q):
  a smaller minute's allowance;
- all requests together: a daily cap, reset at midnight UTC.

The site's own pages are never limited: a browser marks the requests a page
makes on its own site (Sec-Fetch-Site: same-origin), and one typed into the
address bar ("none"). A program can copy that header, which is fine: the
limit is a courtesy for an open catalog, not a lock. Writes need a signed-in
account whatever the key.

The limits' counts are kept in memory, one process serving; a deploy starts
them afresh. usage.py keeps a daily record per caller for admins, an address
only as a pseudonym and its network.
"""

import math
import time
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select

from openlarder import usage
from openlarder.auth import hash_token
from openlarder.config import Settings, get_settings
from openlarder.db import Session
from openlarder.models import ApiKey

KEY_PREFIX = "ol_"
# Paths that sign in and out: a browser's, never a program's to count.
_UNCOUNTED = ("/api/auth/",)
SEARCH_PATHS = ("/api/search",)
TOUCH_EVERY = timedelta(hours=1)

# Bucket name -> (tokens left, when last filled).
_buckets: dict[str, tuple[float, float]] = {}
# Caller -> (UTC day, requests that day).
_days: dict[str, tuple[str, int]] = {}
_last_sweep = 0.0


def reset() -> None:
    """Forget every count (tests)."""
    _buckets.clear()
    _days.clear()


def _sweep(now: float, today: str) -> None:
    """Drop full buckets and past days, so the tables don't grow without end."""
    global _last_sweep
    if now - _last_sweep < 60:
        return
    _last_sweep = now
    for name, (_, at) in list(_buckets.items()):
        if now - at > 120:
            del _buckets[name]
    for name, (day, _) in list(_days.items()):
        if day != today:
            del _days[name]


def _take(name: str, per_minute: int) -> tuple[bool, int, float]:
    """A token bucket: per_minute at once, refilling over a minute. Returns
    whether there was a token, how many are left, and the seconds until the
    next one."""
    now = time.monotonic()
    tokens, at = _buckets.get(name, (float(per_minute), now))
    tokens = min(float(per_minute), tokens + (now - at) * per_minute / 60)
    if tokens < 1:
        _buckets[name] = (tokens, now)
        return False, 0, (1 - tokens) * 60 / per_minute
    _buckets[name] = (tokens - 1, now)
    return True, int(tokens - 1), 0.0


def _address(request: Request) -> str:
    """The visitor's address: Cloudflare's header, then the first forwarded
    one, then the connection's (in development)."""
    if found := request.headers.get("cf-connecting-ip"):
        return found.strip()
    if forwarded := request.headers.get("x-forwarded-for"):
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _given_key(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.headers.get("x-api-key", "").strip() or None


def is_search(request: Request) -> bool:
    """The expensive kind: the search, or a list searched by words."""
    return request.url.path.startswith(SEARCH_PATHS) or bool(
        request.query_params.get("q", "").strip()
    )


def limits(settings: Settings, keyed: bool) -> tuple[int, int, int]:
    """(reads a minute, searches a minute, requests a day)."""
    if keyed:
        return (
            settings.api_key_reads_per_minute,
            settings.api_key_searches_per_minute,
            settings.api_key_requests_per_day,
        )
    return (
        settings.api_reads_per_minute,
        settings.api_searches_per_minute,
        settings.api_requests_per_day,
    )


def _refuse(message: str, wait: float, headers: dict[str, str]) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        message,
        headers={
            **headers,
            "Retry-After": str(max(1, math.ceil(wait))),
            "Cache-Control": "no-store",
        },
    )


async def rate_limit(request: Request, response: Response, session: Session) -> None:
    """For every route: limit /api reads by others than the site's pages."""
    path = request.url.path
    if not path.startswith("/api/") or path.startswith(_UNCOUNTED):
        return
    given = _given_key(request)
    if given is None and request.headers.get("sec-fetch-site") in ("same-origin", "none"):
        return
    if given is not None:
        key = (
            await session.scalar(select(ApiKey).where(ApiKey.token_hash == hash_token(given)))
            if given.startswith(KEY_PREFIX)
            else None
        )
        if key is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "That API key isn't one. Make one on Your account.",
                headers={"Cache-Control": "no-store"},
            )
        now = datetime.now(UTC)
        if key.last_used_at is None or now - key.last_used_at > TOUCH_EVERY:
            key.last_used_at = now
            await session.commit()
        caller, key_id, address = f"key:{key.id}", key.id, None
    else:
        address = _address(request)
        # Counted under a pseudonym of the address, never the address.
        caller, key_id = f"ip:{usage.pseudonym(address)}", None
    reads, searches, per_day = limits(get_settings(), keyed=given is not None)
    search = is_search(request)
    per_minute = searches if search else reads
    policy = f"{per_minute};w=60, {per_day};w=86400"
    raise_it = "" if given else " A free API key, from Your account, raises it."

    clock = datetime.now(UTC)
    today = clock.date().isoformat()
    _sweep(time.monotonic(), today)
    day, used = _days.get(caller, (today, 0))
    if day != today:
        used = 0
    if used >= per_day:
        midnight = datetime.combine(clock.date() + timedelta(days=1), datetime.min.time(), UTC)
        headers = {
            "RateLimit-Limit": str(per_day),
            "RateLimit-Remaining": "0",
            "RateLimit-Policy": policy,
        }
        usage.record(caller, key_id, address, search=search, refused=True)
        raise _refuse(
            f"Over {per_day:,} requests today (UTC).{raise_it}",
            (midnight - clock).total_seconds(),
            headers,
        )
    allowed, left, wait = _take(f"{caller}:{'search' if search else 'read'}", per_minute)
    headers = {
        "RateLimit-Limit": str(per_minute),
        "RateLimit-Remaining": str(left),
        "RateLimit-Policy": policy,
    }
    if not allowed:
        usage.record(caller, key_id, address, search=search, refused=True)
        kind = "searches" if search else "requests"
        raise _refuse(f"Over {per_minute} {kind} a minute.{raise_it}", wait, headers)
    _days[caller] = (today, used + 1)
    usage.record(caller, key_id, address, search=search, refused=False)
    response.headers.update(headers)
