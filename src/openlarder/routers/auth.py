"""Sign-in through the broker: the OpenID Connect authorization code flow.

/login redirects to the broker with state, a nonce and a PKCE challenge.
/callback checks all three, checks the ID token's signature, issuer, audience
and expiry, then starts a session. /logout ends the session here and sends
the browser on to the broker to end its session there. A failure of any kind
sends the browser to /sign-in-failed and logs why; it never says why to the
browser, which is the party that might be forging it.

Signing in comes back to the page it began on (*Ray's round 2 spec,
2026-11-13*). Each sign-in link gives /login that page as ``next``; what
passes auth.safe_next is kept in the sign-in cookie, which is signed, beside
the state, and the callback redirects to it. It is never read from the
callback's own address, so nothing on the way to the broker and back can
change it. Someone with no display name yet goes to /welcome first, and
/continue takes them on from there. The cookie lasts an hour, so a name
chosen later than that goes to the front page.

A sign-in is counted without a page of its own: the callback marks the
address it sends the browser to, "#signed-in=new" or "#signed-in=returning",
which the analytics loader takes off again and turns into an event
(analytics.py). It names nobody, and isn't added where nothing counts. Not
a cookie, which the spec asked for: SCOPING.md brings a consent banner
with any cookie that's for analytics (*Ray, 2026-11-13*).
"""

import logging
from typing import Annotated

import httpx2
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.starlette_client import StarletteOAuth2App
from fastapi import APIRouter, Cookie, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from joserfc.errors import JoseError
from pydantic import BaseModel

from openlarder import agreement, analytics, roles
from openlarder.auth import (
    CALLBACK_PATH,
    FAILED,
    SESSION_COOKIE,
    SESSION_LIFETIME,
    WELCOME,
    CurrentUser,
    get_oidc_client,
    optional_oidc_client,
    safe_next,
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
    # Their role (roles.py), and what it lets them do, so the SPA needn't
    # know the ladder: edit the catalog (moderator), run the site (admin),
    # claim requests (contributor), and the roles they may give.
    role: str
    may_edit: bool
    may_run: bool
    may_claim: bool
    grants: list[str]
    # Whether they've accepted the contributor agreement as it reads now,
    # which adding to the catalog needs (agreement.py).
    agreed: bool = False
    # A contributor whose additions publish without review (trust.py).
    trusted: bool = False
    # Their buy-link shops: {"order": [...], "hidden": [...]}, or None.
    shops: dict | None = None
    # The grocer they chose for ingredients' links (grocery.py), or None.
    grocer: str | None = None


def me_for(user: User, settings: Settings) -> Me:
    issuer = settings.oidc_issuer
    return Me(
        id=str(user.id),
        display_name=user.display_name,
        suggested_name=user.suggested_name if user.display_name is None else None,
        account_url=issuer.rstrip("/") + "/settings" if issuer else None,
        role=user.role,
        may_edit=user.may_edit,
        may_run=user.at_least("admin"),
        may_claim=user.may_claim,
        grants=roles.grantable(user.role),
        agreed=agreement.has_agreed(user),
        trusted=user.trusted,
        shops=(
            {k: prefs[k] for k in ("order", "hidden")}
            if (prefs := user.shop_preferences or {}).get("order") is not None
            else None
        ),
        grocer=prefs.get("grocer"),
    )


def callback_url(request: Request, settings: Settings) -> str:
    if settings.public_url:
        return settings.public_url + CALLBACK_PATH
    return str(request.url_for("auth_callback"))


def home_url(request: Request, settings: Settings) -> str:
    """The front page, absolute, for the broker to send people back to."""
    return (settings.public_url or str(request.base_url).rstrip("/")) + "/"


# The sign-in cookie's name for the page to come back to.
NEXT = "next"


def _taken_next(request: Request) -> str:
    """The page sign-in began on, once: checked again on the way out, in
    case what's refused has changed since it was kept."""
    return safe_next(request.session.pop(NEXT, None)) or "/"


@router.get("/login")
async def login(
    request: Request,
    settings: Config,
    broker: Broker,
    wanted: Annotated[
        str | None,
        Query(alias="next", description="The page to come back to: a path on this site."),
    ] = None,
    again: Annotated[
        bool,
        Query(description="Keep the page the last try was coming back to; `next` is ignored."),
    ] = False,
) -> Response:
    # "Try again" on /sign-in-failed has no page of its own to give: the
    # one the failed try kept stands. Any other link replaces it, or
    # clears it, so an old one never outlives the sign-in it was for.
    if not again:
        if kept := safe_next(wanted):
            request.session[NEXT] = kept
        else:
            request.session.pop(NEXT, None)
    return await broker.authorize_redirect(request, callback_url(request, settings))


@router.get("/callback", name="auth_callback")
async def callback(
    request: Request, session: Session, settings: Config, broker: Broker
) -> Response:
    try:
        token = await broker.authorize_access_token(request)
    except (AuthlibBaseError, JoseError, httpx2.HTTPError) as exc:
        log.warning("sign-in refused: %r", exc)
        return RedirectResponse(FAILED, status.HTTP_303_SEE_OTHER)

    claims = token.get("userinfo")
    # No ID token means nothing above checked who this is; an access token
    # alone does not say. The issuer is compared with the configured one, not
    # only with whatever the discovery document claimed.
    if not claims or claims.get("iss") != settings.oidc_issuer or not claims.get("sub"):
        log.warning("sign-in refused: no usable ID token")
        return RedirectResponse(FAILED, status.HTTP_303_SEE_OTHER)

    signed = await sign_in(
        session, claims["iss"], claims["sub"], suggested_name_from(claims), token.get("id_token")
    )
    await session.commit()

    # Someone with no name yet is asked for one first; the page they began
    # on stays in the sign-in cookie for /continue.
    target = _taken_next(request) if signed.named else WELCOME
    if analytics.counting(settings):
        # safe_next lets no "#" through, so this is the address's only one.
        target += analytics.signed_in_mark(new=signed.new)
    response = RedirectResponse(target, status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SESSION_COOKIE,
        signed.token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
        httponly=True,
        secure=callback_url(request, settings).startswith("https://"),
        samesite="lax",
    )
    return response


@router.get("/continue")
async def carry_on(request: Request) -> Response:
    """From the welcome page, once a name is chosen: on to the page sign-in
    began on, or the front page."""
    return RedirectResponse(_taken_next(request), status.HTTP_303_SEE_OTHER)


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
