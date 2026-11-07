"""Sign-in through the broker: the OpenID Connect authorization code flow.

/login redirects to the broker with state, a nonce and a PKCE challenge.
/callback checks all three, checks the ID token's signature, issuer, audience
and expiry, then starts a session. A failure of any kind sends the browser
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
    display_name_from,
    get_oidc_client,
    sign_in,
    sign_out,
)
from openlarder.config import Settings, get_settings
from openlarder.db import Session

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

Broker = Annotated[StarletteOAuth2App, Depends(get_oidc_client)]
Config = Annotated[Settings, Depends(get_settings)]


class Me(BaseModel):
    id: str
    display_name: str


def callback_url(request: Request, settings: Settings) -> str:
    if settings.public_url:
        return settings.public_url + CALLBACK_PATH
    return str(request.url_for("auth_callback"))


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

    raw = await sign_in(session, claims["iss"], claims["sub"], display_name_from(claims))
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
async def me(user: CurrentUser) -> Me:
    return Me(id=str(user.id), display_name=user.display_name)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session: Session,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Response:
    if token:
        await sign_out(session, token)
        await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
