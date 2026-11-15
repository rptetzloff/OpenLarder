"""Telling Google Ads which ad clicks led to a new account, with none of
Google's script on the site. *Decided by Ray, 2026-11-13* (round 4, part E):
"route B", offline conversion import.

Off unless OPENLARDER_AD_CLICKS is set. With it:

1. Google adds a click id to the address an ad sends someone to (?gclid=…,
   or gbraid or wbraid from an app). The middleware here keeps it in a
   cookie of the site's own, ol_ad_click, for 90 days. Nothing is sent to
   Google, and no JavaScript is involved.
2. If that browser makes a new account in that time, the sign-in callback
   (routers/auth.py) adds one row to ad_conversions: the click id, when it
   was clicked and when the account was made. The row has no user column
   and nothing else an account could be found by.
3. A scheduled export (scripts/ads_export.sql, as the ads_exporter role)
   copies new rows to a sheet that Google Ads reads.
4. A row is deleted 90 days after its sign-up: a click id is no use to
   Google after that.

Ray's rules for when nothing is kept: the browser asks not to be tracked
(Sec-GPC or DNT, as analytics.py has it); the visitor is in the EEA, the UK
or Switzerland, where an advertising cookie needs consent first and the
site has no prompt; or they're signed in already.

Claude's choices on top of those, 2026-11-15:

- **No country, no cookie.** The country is Cloudflare's CF-IPCountry
  header. Without it (a request that didn't come through Cloudflare, or
  its IP Geolocation switched off), or with its "XX" (unknown) or "T1"
  (Tor), nobody can say the visitor is outside those countries, so nothing
  is kept. What it costs: a local test has to send the header.
- The country list also has the territories with a code of their own
  where the same law runs, or the UK's does in all but name (COUNTRIES).
- **Signed in is told by the session cookie being there**, not by asking
  the database on an ad's landing page. A cookie that outlived its session
  errs toward keeping nothing; and only a *new* account ever adds a row.
- **The same rules are asked again at sign-up**, so someone who has
  switched on Global Privacy Control since the click adds no row.
- **The sign-up's time is kept to the minute, rounded up.** The account's
  own created_at is the same now() to the microsecond, which would join
  the two tables as well as a user column would. Up, not down: a sign-up
  in the same minute as its click would otherwise be dated before the
  click, and Google refuses a conversion that precedes its click. This
  doesn't make the row untraceable: on a quiet day, whoever can read the
  whole database could still pair a sign-up with an account by the minute.
- Any sign-in clears the cookie, not only one that adds a row: once
  someone has an account it has no further use.

What this can't see: whether Google accepts a row. A made-up click id is
refused there, so that is checked with one real click (README.md).
"""

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from itsdangerous import BadSignature, Signer
from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response

from openlarder.auth import SESSION_COOKIE
from openlarder.config import Settings, get_settings
from openlarder.models import AdConversion

log = logging.getLogger(__name__)

COOKIE = "ol_ad_click"
# Asked for in this order; the first one the address has is the one kept.
TYPES = ("gclid", "gbraid", "wbraid")
# What a click id looks like. Kept exactly as it came: they're case sensitive.
SHAPE = re.compile(r"[A-Za-z0-9_-]{10,512}")
# How long the cookie lasts, how long a click may be credited, and how long
# a row is kept. Google's click-through window for the conversion has to be
# at least this (README.md).
KEEP = timedelta(days=90)
# Not pages: the API, the buy-link redirects, the build's files.
NOT_PAGES = ("/api/", "/go/", "/assets/")
# Two instances' clocks may differ a little; a click can't be from later
# than that.
SKEW = 300
# The signing key is the sign-in cookie's; the salt keeps a value signed
# for one from being accepted as the other.
SALT = "ol_ad_click"
# How often rows past KEEP are deleted. Ray asked for daily; this often
# costs nothing and gets past a try that failed.
PRUNE_EVERY = 6 * 3600

# Where an advertising cookie needs consent first, by Cloudflare's country
# code. One list, so it's changed in one place. The EU's 27, the rest of
# the EEA, the UK and Switzerland are Ray's (2026-11-13).
EU = frozenset(
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split()
)
EEA_UK_CH = EU | frozenset({"IS", "LI", "NO", "GB", "CH"})
# Claude's additions: places with a code of their own where EU law runs
# (Åland, and France's overseas regions and Saint Martin), and Gibraltar,
# Jersey, Guernsey and the Isle of Man, whose laws follow the UK's.
TERRITORIES = frozenset("AX GF GP MQ RE YT MF GI JE GG IM".split())
COUNTRIES = EEA_UK_CH | TERRITORIES
# Cloudflare's codes for "unknown" and for Tor.
NOWHERE = frozenset({"XX", "T1"})


@dataclass(frozen=True)
class Click:
    type: str
    # Unix seconds.
    at: int
    id: str


def click_in(query: Mapping[str, str]) -> tuple[str, str] | None:
    """The click id an address carries, and its type: the first of TYPES
    that's there, if it looks like one. One that doesn't isn't passed over
    for the next: an address Google wrote has a well-formed one."""
    for name in TYPES:
        if name in query:
            value = query[name]
            return (name, value) if SHAPE.fullmatch(value) else None
    return None


def may_keep(headers: Mapping[str, str]) -> bool:
    """Whether this visitor's click may be kept: they haven't asked not to
    be tracked, and they're known to be outside COUNTRIES."""
    if headers.get("sec-gpc", "").strip() == "1" or headers.get("dnt", "").strip() == "1":
        return False
    country = headers.get("cf-ipcountry", "").strip().upper()
    return bool(country) and country not in NOWHERE and country not in COUNTRIES


def _signer(secret: str) -> Signer:
    return Signer(secret, salt=SALT, digest_method=hashlib.sha256)


def sealed(secret: str, type_: str, click_id: str, now: float) -> str:
    """The cookie's value: <type>.<unix seconds>.<click id>, signed."""
    return _signer(secret).sign(f"{type_}.{int(now)}.{click_id}").decode()


def opened(secret: str, value: str, now: float) -> Click | None:
    """The click a cookie holds, if this site signed it and it's no older
    than KEEP. Anything else is nothing: a cookie somebody edited, one
    signed with another key, one a browser kept too long."""
    try:
        plain = _signer(secret).unsign(value).decode()
    except (BadSignature, UnicodeError):
        return None
    type_, _, rest = plain.partition(".")
    at, _, click_id = rest.partition(".")
    if type_ not in TYPES or not at.isascii() or not at.isdigit() or not SHAPE.fullmatch(click_id):
        return None
    if not now - KEEP.total_seconds() <= int(at) <= now + SKEW:
        return None
    return Click(type_, int(at), click_id)


def at_sign_up(request: Request, settings: Settings, now: float | None = None) -> Click | None:
    """The ad click behind a sign-up, if there's one that may be recorded."""
    value = request.cookies.get(COOKIE)
    if not settings.ad_clicks or not settings.session_secret or not value:
        return None
    if not may_keep(request.headers):
        return None
    return opened(settings.session_secret, value, time.time() if now is None else now)


async def record(session: AsyncSession, click: Click) -> None:
    """One row for a new account's ad click, in the caller's transaction.
    A click that has a row already adds nothing."""
    await session.execute(
        insert(AdConversion)
        .values(
            kind="sign_up",
            click_id=click.id,
            click_id_type=click.type,
            clicked_at=datetime.fromtimestamp(click.at, UTC),
            # To the minute, rounded up: see the module's docstring.
            converted_at=func.date_trunc("minute", func.now()) + timedelta(minutes=1),
        )
        .on_conflict_do_nothing(index_elements=["kind", "click_id"])
    )


async def prune(session: AsyncSession) -> int:
    """Delete rows whose sign-up was more than KEEP ago; how many went."""
    gone = await session.execute(
        delete(AdConversion).where(AdConversion.converted_at < func.now() - KEEP)
    )
    await session.commit()
    return gone.rowcount


async def keep_pruning(factory: async_sessionmaker) -> None:
    """The app's background task. It runs whether or not the setting is on:
    switching the feature off mustn't keep its rows for good."""
    while True:
        try:
            async with factory() as session:
                await prune(session)
        except Exception:
            log.exception("Deleting old ad sign-ups failed")
        await asyncio.sleep(PRUNE_EVERY)


def secure(settings: Settings, scheme: str) -> bool:
    """Whether the cookie is for https only: as the session cookie decides
    it, from the public address, since behind the proxy the app sees http."""
    return (settings.public_url or f"{scheme}://").startswith("https://")


def _may_carry(query: bytes) -> bool:
    """A cheap look, so a request with no click id costs nothing more."""
    return any(name.encode() + b"=" in query for name in TYPES)


class Middleware:
    """Keeps an ad's click id from a page's address in the cookie."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        value = self._to_keep(scope) if scope["type"] == "http" else None
        if value is None:
            await self.app(scope, receive, send)
            return

        async def kept(message) -> None:
            if message["type"] == "http.response.start" and message["status"] < 400:
                headers = MutableHeaders(scope=message)
                # A page, told by what was sent: the SPA's catch-all route
                # serves the build's other files too (an icon, robots.txt),
                # and those aren't pages. What this leaves out: a redirect,
                # which has no type and drops the click id from the address
                # anyway.
                if headers.get("content-type", "").startswith("text/html"):
                    headers.append("set-cookie", value)
                    # The cookie is this visitor's alone. A page is sent
                    # no-cache, which lets a shared cache keep it and ask
                    # each time; one that kept this would hand the click,
                    # signed, to whoever asked next.
                    headers["cache-control"] = "no-store"
            await send(message)

        await self.app(scope, receive, kept)

    def _to_keep(self, scope) -> str | None:
        """The Set-Cookie header for this request, or None for most."""
        if scope["method"] != "GET" or not _may_carry(scope["query_string"]):
            return None
        if scope["path"].startswith(NOT_PAGES):
            return None
        # As the routes get them, so a test's settings are these too.
        settings = scope["app"].dependency_overrides.get(get_settings, get_settings)()
        if not settings.ad_clicks or not settings.session_secret:
            return None
        request = Request(scope)
        found = click_in(request.query_params)
        if found is None or SESSION_COOKIE in request.cookies or not may_keep(request.headers):
            return None
        # A newer click replaces an older one: same name, same path.
        carrier = Response()
        carrier.set_cookie(
            COOKIE,
            sealed(settings.session_secret, *found, time.time()),
            max_age=int(KEEP.total_seconds()),
            path="/",
            httponly=True,
            secure=secure(settings, scope["scheme"]),
            samesite="lax",
        )
        return carrier.headers["set-cookie"]
