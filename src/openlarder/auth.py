"""Sessions and the signed-in user.

A session is a random token in an HttpOnly cookie; the database keeps only
its SHA-256. Sessions last 30 days from sign-in and are not extended by use.
Signing out deletes the session here. It does not sign anyone out of the
broker, so the next "Sign in" may go straight through without a password.
"""

import hashlib
import secrets
from datetime import timedelta
from functools import lru_cache
from typing import Annotated, Any

import httpx2
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.config import Settings, get_settings
from openlarder.db import Session
from openlarder.models import User, UserSession

SESSION_COOKIE = "openlarder_session"
# The cookie Starlette's SessionMiddleware keeps state and nonce in between
# the redirect to the broker and the callback. Nothing else is put in it.
SIGN_IN_COOKIE = "openlarder_sign_in"
CALLBACK_PATH = "/api/auth/callback"
SESSION_LIFETIME = timedelta(days=30)
FALLBACK_NAME = "OpenLarder user"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def display_name_from(claims: dict[str, Any]) -> str:
    for key in ("name", "preferred_username"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return FALLBACK_NAME


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


def get_oidc_client(settings: Annotated[Settings, Depends(get_settings)]) -> StarletteOAuth2App:
    if not settings.sign_in_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in is not configured.")
    assert settings.oidc_client_id and settings.oidc_client_secret and settings.oidc_issuer
    return _cached_client(
        settings.oidc_issuer, settings.oidc_client_id, settings.oidc_client_secret
    )


async def sign_in(session: AsyncSession, issuer: str, subject: str, name: str) -> str:
    """Find or create the user, start a session, and return its raw token."""
    user_id = await session.scalar(
        insert(User)
        .values(issuer=issuer, subject=subject, display_name=name)
        .on_conflict_do_update(index_elements=["issuer", "subject"], set_={"display_name": name})
        .returning(User.id)
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
        )
    )
    await session.flush()
    return token


async def sign_out(session: AsyncSession, token: str) -> None:
    await session.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))


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
