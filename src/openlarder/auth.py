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
from datetime import timedelta
from functools import lru_cache
from typing import Annotated, Any

import httpx2
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import names
from openlarder.config import Settings, get_settings
from openlarder.db import Session
from openlarder.models import User, UserSession

SESSION_COOKIE = "openlarder_session"
# The cookie Starlette's SessionMiddleware keeps state and nonce in between
# the redirect to the broker and the callback. Nothing else is put in it.
SIGN_IN_COOKIE = "openlarder_sign_in"
CALLBACK_PATH = "/api/auth/callback"
SESSION_LIFETIME = timedelta(days=30)


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


async def sign_in(
    session: AsyncSession, issuer: str, subject: str, suggested: str | None, id_token: str | None
) -> str:
    """Find or create the user, start a session, and return its raw token.

    The broker's name only ever refreshes the suggestion. Once someone has
    chosen a display name, signing in never touches it.
    """
    stmt = insert(User).values(issuer=issuer, subject=subject, suggested_name=suggested)
    user_id = await session.scalar(
        stmt.on_conflict_do_update(
            index_elements=["issuer", "subject"],
            set_={
                "suggested_name": case(
                    (User.display_name.is_(None), stmt.excluded.suggested_name), else_=None
                )
            },
        ).returning(User.id)
    )
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
    return token


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
    return await session.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.token_hash == hash_token(token), UserSession.expires_at > func.now())
    )


async def require_user(user: Annotated[User | None, Depends(current_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return user


CurrentUser = Annotated[User, Depends(require_user)]


async def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can do that yet.")
    return user


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
