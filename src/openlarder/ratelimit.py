"""Rate limits on the public API (SCOPING.md, API).

Anyone may read /api without a key, at api_limit_anonymous requests a minute
per address; a key (Authorization: Bearer ol_..., or X-API-Key) raises it to
api_limit_key a minute. *Ray, 2026-11-09.* The site's own pages are never
limited: a browser marks the requests a page makes on its own site
(Sec-Fetch-Site: same-origin), and one typed into the address bar ("none").
That header can be copied by a program, which is fine: the limit is a
courtesy for an open catalog, not a lock, and the data dumps are the way to
take everything.

Counts are kept in memory, one process serving, and never stored; an
address is seen only as a key to its count.
"""

import math
import time
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select

from openlarder.auth import hash_token
from openlarder.config import get_settings
from openlarder.db import Session
from openlarder.models import ApiKey

KEY_PREFIX = "ol_"
# Paths that sign in and out: a browser's, never a program's to count.
_UNCOUNTED = ("/api/auth/",)
TOUCH_EVERY = timedelta(hours=1)

# Bucket name -> (tokens left, when last filled).
_buckets: dict[str, tuple[float, float]] = {}
_last_sweep = 0.0


def reset() -> None:
    """Forget every count (tests)."""
    _buckets.clear()


def _sweep(now: float) -> None:
    """Drop buckets full again, so the table doesn't grow without end."""
    global _last_sweep
    if now - _last_sweep < 60:
        return
    _last_sweep = now
    for name, (_, at) in list(_buckets.items()):
        if now - at > 120:
            del _buckets[name]


def _take(name: str, per_minute: int) -> tuple[bool, int, float]:
    """A token bucket: per_minute at once, refilling over a minute. Returns
    whether there was a token, how many are left, and the seconds until the
    next one."""
    now = time.monotonic()
    _sweep(now)
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


async def rate_limit(request: Request, response: Response, session: Session) -> None:
    """For every route: limit /api reads by others than the site's pages."""
    path = request.url.path
    if not path.startswith("/api/") or path.startswith(_UNCOUNTED):
        return
    given = _given_key(request)
    if given is None and request.headers.get("sec-fetch-site") in ("same-origin", "none"):
        return
    settings = get_settings()
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
        name, limit = f"key:{key.id}", settings.api_limit_key
    else:
        name, limit = f"ip:{_address(request)}", settings.api_limit_anonymous
    allowed, left, wait = _take(name, limit)
    headers = {"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": str(left)}
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Over {limit} requests a minute. "
            + ("A free API key, from Your account, raises it." if given is None else "Slow down."),
            headers={**headers, "Retry-After": str(math.ceil(wait)), "Cache-Control": "no-store"},
        )
    response.headers.update(headers)
