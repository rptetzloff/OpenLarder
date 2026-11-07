"""Sign-in through the broker: the OpenID Connect authorization code flow.

/login redirects to the broker with state, a nonce and a PKCE challenge.
/callback checks all three, checks the ID token's signature, issuer, audience
and expiry, then starts a session. /logout ends the session here and sends
the browser on to the broker to end its session there. A failure of any kind sends the browser
back to the front page with ?sign-in=failed and logs why; it never says why
to the browser, which is the party that might be forging it.
"""

import logging
from typing import Annotated

import httpx2
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.starlette_client import StarletteOAuth2App
from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from joserfc.errors import JoseError
from pydantic import BaseModel

from openlarder.auth import (
    CALLBACK_PATH,
    SESSION_COOKIE,
    SESSION_LIFETIME,
    CurrentUser,
    get_oidc_client,
    optional_oidc_client,
    sign_in,
    sign_out,
    suggested_name_from,
)
from openlarder.config import Settings, get_settings
from openlarder.db import Session
from openlarder.models import User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

Broker = Annotated[StarletteOAuth2App, Depends(get_oidc_client)]
OptionalBroker = Annotated[StarletteOAuth2App | None, Depends(optional_oidc_client)]
Config = Annotated[Settings, Depends(get_settings)]


class Me(BaseModel):
    id: str
    # None until the person chooses one; the SPA then asks for it.
    display_name: str | None
    suggested_name: str | None
    # Where to manage sign-in methods and passkeys: Authgear's own page.
    account_url: str | None
    # May add to the catalog directly, until review exists.
    is_admin: bool


def me_for(user: User, settings: Settings) -> Me:
    issuer = settings.oidc_issuer
    return Me(
        id=str(user.id),
        display_name=user.display_name,
        suggested_name=user.suggested_name if user.display_name is None else None,
        account_url=issuer.rstrip("/") + "/settings" if issuer else None,
        is_admin=user.is_admin,
    )


def callback_url(request: Request, settings: Settings) -> str:
    if settings.public_url:
        return settings.public_url + CALLBACK_PATH
    return str(request.url_for("auth_callback"))


def home_url(request: Request, settings: Settings) -> str:
    """The front page, absolute, for the broker to send people back to."""
    return (settings.public_url or str(request.base_url).rstrip("/")) + "/"


@router.get("/login")
async def login(request: Request, settings: Config, broker: Broker) -> Response:
    return await broker.authorize_redirect(request, callback_url(request, settings))


@router.get("/callback", name="auth_callback")
async def callback(
    request: Request, session: Session, settings: Config, broker: Broker
) -> Response:
    try:
        token = await broker.authorize_access_token(request)
    except (AuthlibBaseError, JoseError, httpx2.HTTPError) as exc:
        log.warning("sign-in refused: %r", exc)
        return RedirectResponse("/?sign-in=failed", status.HTTP_303_SEE_OTHER)

    claims = token.get("userinfo")
    # No ID token means nothing above checked who this is; an access token
    # alone does not say. The issuer is compared with the configured one, not
    # only with whatever the discovery document claimed.
    if not claims or claims.get("iss") != settings.oidc_issuer or not claims.get("sub"):
        log.warning("sign-in refused: no usable ID token")
        return RedirectResponse("/?sign-in=failed", status.HTTP_303_SEE_OTHER)

    raw = await sign_in(
        session, claims["iss"], claims["sub"], suggested_name_from(claims), token.get("id_token")
    )
    await session.commit()

    response = RedirectResponse("/", status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
        httponly=True,
        secure=callback_url(request, settings).startswith("https://"),
        samesite="lax",
    )
    return response


@router.get("/me", response_model=Me)
async def me(user: CurrentUser, settings: Config) -> Me:
    return me_for(user, settings)


@router.post("/logout")
async def logout(
    request: Request,
    session: Session,
    settings: Config,
    broker: OptionalBroker,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Response:
    # The session here ends first, whatever happens next: a broker that
    # cannot be reached leaves someone signed in there, never here.
    ended = await sign_out(session, token) if token else None
    if ended is not None:
        await session.commit()

    target = "/"
    # No session here means nothing to end at the broker either: sending the
    # browser on anyway would land a signed-out person on its login page.
    if broker is not None and ended is not None and ended.found:
        try:
            if ended.id_token:
                # Authentik, used before Authgear, refuses a post_logout_redirect_uri
                # that comes without id_token_hint ("The request is otherwise
                # malformed"). Authgear accepts either.
                logout_url = await broker.create_logout_url(
                    post_logout_redirect_uri=home_url(request, settings),
                    id_token_hint=ended.id_token,
                )
            else:
                # A session from before ID tokens were kept: the broker can
                # still end its session, but will not send anyone back.
                logout_url = await broker.create_logout_url()
            target = logout_url["url"]
        except (httpx2.HTTPError, RuntimeError) as exc:
            log.warning("signed out here only; broker end-session unavailable: %r", exc)

    # 303 so the browser follows with a GET, not a repeat of this POST.
    response = RedirectResponse(target, status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
