"""Sessions and the signed-in user.

A session is a random token in an HttpOnly cookie; the database keeps only
its SHA-256. Sessions last 30 days from sign-in and are not extended by use.
Signing out deletes the session here, then sends the browser to the
broker's end-session endpoint so the broker's session ends too, with the
session's ID token as id_token_hint so the broker will send them back.
Whether the broker's session ends is its configuration, not this code's
(Authentik, used before Authgear, needed a User Logout stage for it).
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from typing import Annotated, Any
from urllib.parse import unquote, urlsplit

import httpx2
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import history, names
from openlarder.config import Settings, get_settings
from openlarder.db import Session
from openlarder.models import User, UserSession

SESSION_COOKIE = "openlarder_session"
# The cookie Starlette's SessionMiddleware keeps state and nonce in between
# the redirect to the broker and the callback, and the page to come back
# to after (safe_next). Nothing else is put in it.
SIGN_IN_COOKIE = "openlarder_sign_in"
CALLBACK_PATH = "/api/auth/callback"
SESSION_LIFETIME = timedelta(days=30)


# Sign-in's own pages. Coming back to one would tell someone it had just
# worked for that it hadn't, or ask a named person for a name.
WELCOME = "/welcome"
FAILED = "/sign-in-failed"
NEXT_MAX = 512


def _reads_as_elsewhere(text: str) -> bool:
    return "//" in text or "\\" in text or any(ord(c) < 32 or ord(c) == 127 for c in text)


def safe_next(value: object) -> str | None:
    """Where to go back to after signing in, if it's a page of this site;
    None for anything else, which sends people to the front page.

    The value comes from a link anyone can write, and the callback redirects
    to it, so one that a browser could read as another site's address is
    refused whole, never repaired: a second slash ("//evil.example" is
    another host), a backslash (browsers read "/\\evil.example" the same
    way), a control character (browsers drop a tab or a newline from an
    address, which can bring two slashes together). The path is looked at
    again with its percent-escapes read, as the server reads them before
    choosing a route. Nor the API or a buy link: /go/ would send someone on
    to a shop and count a click nobody made. Nor one with a "#": the
    site's links never send one, and the callback may add its own
    (analytics.signed_in_mark).

    Stricter than it must be: a search for "a//b" isn't come back to. The
    site's own links escape a slash in what was typed, so that takes an
    address written by hand.
    """
    if not isinstance(value, str) or len(value) > NEXT_MAX:
        return None
    if not value.startswith("/") or "#" in value or _reads_as_elsewhere(value):
        return None
    parts = urlsplit(value)
    path = unquote(parts.path)
    if parts.scheme or parts.netloc or _reads_as_elsewhere(path):
        return None
    path = path.rstrip("/").lower()
    if path in (WELCOME, FAILED) or any(
        path == under or path.startswith(under + "/") for under in ("/api", "/go")
    ):
        return None
    return value


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def suggested_name_from(claims: dict[str, Any]) -> str | None:
    """The broker's name for someone, if it would pass as a display name."""
    for key in ("name", "preferred_username"):
        value = claims.get(key)
        if isinstance(value, str) and (name := names.suggestion(value)):
            return name
    return None


def build_oidc_client(
    issuer: str,
    client_id: str,
    client_secret: str,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> StarletteOAuth2App:
    """The broker's client. ``transport`` is for tests, which fake the broker."""
    client_kwargs: dict[str, Any] = {"scope": "openid profile", "code_challenge_method": "S256"}
    if transport is not None:
        client_kwargs["transport"] = transport
    return OAuth().register(
        "broker",
        server_metadata_url=issuer.rstrip("/") + "/.well-known/openid-configuration",
        client_id=client_id,
        client_secret=client_secret,
        client_kwargs=client_kwargs,
    )


# One per process, so the broker's metadata and keys are fetched once rather
# than on every sign-in. Authlib refetches the keys when a token names one it
# has not seen, which covers the broker rotating them.
_cached_client = lru_cache(build_oidc_client)


def optional_oidc_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StarletteOAuth2App | None:
    if not settings.sign_in_configured:
        return None
    assert settings.oidc_client_id and settings.oidc_client_secret and settings.oidc_issuer
    return _cached_client(
        settings.oidc_issuer, settings.oidc_client_id, settings.oidc_client_secret
    )


def get_oidc_client(
    client: Annotated[StarletteOAuth2App | None, Depends(optional_oidc_client)],
) -> StarletteOAuth2App:
    if client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in is not configured.")
    return client


@dataclass(frozen=True)
class SignedIn:
    # The session's raw token, for the cookie.
    token: str
    # This sign-in made the account.
    new: bool
    # They've chosen a display name. Until then they're asked for one.
    named: bool


async def sign_in(
    session: AsyncSession, issuer: str, subject: str, suggested: str | None, id_token: str | None
) -> SignedIn:
    """Find or create the user and start a session.

    The broker's name only ever refreshes the suggestion. Once someone has
    chosen a display name, signing in never touches it.
    """
    # Asked before the upsert, which can't say which it did. Two first
    # sign-ins of one person at the same moment would both read as new;
    # it's only counted (routers/auth.py), so that's left.
    existed = await session.scalar(
        select(User.id).where(User.issuer == issuer, User.subject == subject)
    )
    stmt = insert(User).values(issuer=issuer, subject=subject, suggested_name=suggested)
    user_id, display_name = (
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["issuer", "subject"],
                set_={
                    "suggested_name": case(
                        (User.display_name.is_(None), stmt.excluded.suggested_name), else_=None
                    )
                },
            ).returning(User.id, User.display_name)
        )
    ).one()
    # Expired sessions are swept here rather than by a job: there is no
    # worker yet, and this keeps one user's rows from growing without bound.
    await session.execute(
        delete(UserSession).where(
            UserSession.user_id == user_id, UserSession.expires_at <= func.now()
        )
    )
    token = new_token()
    # The database's clock for both ends, so created_at and expires_at agree
    # with the now() that current_user compares against.
    session.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=func.now() + SESSION_LIFETIME,
            id_token=id_token or None,
        )
    )
    await session.flush()
    return SignedIn(token=token, new=existed is None, named=display_name is not None)


class Ended:
    """What signing out found: whether there was a session, and its ID token."""

    def __init__(self, found: bool, id_token: str | None) -> None:
        self.found = found
        self.id_token = id_token


async def sign_out(session: AsyncSession, token: str) -> Ended:
    result = await session.execute(
        delete(UserSession)
        .where(UserSession.token_hash == hash_token(token))
        .returning(UserSession.id_token)
    )
    row = result.first()
    return Ended(found=row is not None, id_token=row[0] if row else None)


async def current_user(
    session: Session,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User | None:
    if not token:
        return None
    user = await session.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.token_hash == hash_token(token), UserSession.expires_at > func.now())
    )
    # What they change is recorded as theirs (history.py).
    await history.acting(session, user.id if user else None)
    return user


async def require_user(user: Annotated[User | None, Depends(current_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return user


CurrentUser = Annotated[User, Depends(require_user)]
# Whoever is asking, signed in or not: what they see depends on it
# (visibility.py).
Viewer = Annotated[User | None, Depends(current_user)]


async def require_moderator(user: CurrentUser) -> User:
    """Edits the catalog directly (roles.py)."""
    if not user.may_edit:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a moderator can do that yet.")
    return user


async def require_admin(user: CurrentUser) -> User:
    """Runs the site: imports, monitoring (roles.py)."""
    if not user.at_least("admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can do that.")
    return user


ModeratorUser = Annotated[User, Depends(require_moderator)]
AdminUser = Annotated[User, Depends(require_admin)]


def require_same_origin(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    """Refuse a cookie-authenticated change that another site's page sent.

    SameSite=Lax keeps the session cookie off cross-site requests, but not
    off requests from other subdomains of openlarder.com, which count as
    the same site; auth.openlarder.com is Authgear's. Browsers send Origin
    on every POST, PUT and DELETE, so a mismatch is refused. A request with
    no Origin is not from a browser page and has no cookie to ride on.
    """
    origin = request.headers.get("origin")
    expected = settings.public_url or str(request.base_url).rstrip("/")
    if origin is not None and origin != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-origin request refused.")


SameOrigin = Depends(require_same_origin)
