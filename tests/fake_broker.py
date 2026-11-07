"""A fake OpenID provider, and helpers for signing in through it.

The broker is faked at the HTTP layer, below Authlib: it publishes discovery
metadata and a key set, and its token endpoint checks the client secret, the
PKCE verifier and the redirect URI before handing back an RS256 ID token. So
tests exercise Authlib's real checks and the app's real routes; what they
cannot show is that the real broker behaves like the fake. That is checked by
signing in on the deployed site. The fixtures that use it are in conftest.py.
"""

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.auth import SESSION_COOKIE
from openlarder.config import Settings

ISSUER = "https://broker.test/application/o/openlarder/"


CLIENT_ID = "openlarder-test"


CLIENT_SECRET = "s3cret"


class FakeBroker:
    """Just enough of an OpenID provider to sign someone in."""

    def __init__(self) -> None:
        self.key = RSAKey.generate_key(2048, parameters={"kid": "k1"})
        self.codes: dict[str, dict[str, str]] = {}
        self.subject = "subject-1"
        self.name = "Test Cook"
        self.overrides: dict[str, Any] = {}
        self.signing_key = self.key
        self.token_requests = 0
        self.last_id_token = ""
        self.issuer = ISSUER
        self.end_session = True

    def approve(self, authorize_url: str) -> tuple[str, str]:
        """The person signs in at the broker; returns the code and state it redirects with."""
        query = {k: v[0] for k, v in parse_qs(urlsplit(authorize_url).query).items()}
        code = secrets.token_urlsafe(8)
        self.codes[code] = query
        return code, query["state"]

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            metadata = {
                "issuer": self.issuer,
                "authorization_endpoint": "https://broker.test/authorize/",
                "token_endpoint": "https://broker.test/token/",
                "jwks_uri": "https://broker.test/jwks/",
                "id_token_signing_alg_values_supported": ["RS256"],
            }
            if self.end_session:
                metadata["end_session_endpoint"] = "https://broker.test/end-session/"
            return httpx2.Response(200, json=metadata)
        if path == "/jwks/":
            return httpx2.Response(200, json=KeySet([self.key]).as_dict(private=False))
        if path == "/token/":
            self.token_requests += 1
            return self._token(request)
        return httpx2.Response(404)

    def _token(self, request: httpx2.Request) -> httpx2.Response:
        basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        if request.headers.get("authorization") != f"Basic {basic}":
            return httpx2.Response(401, json={"error": "invalid_client"})
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        issued = self.codes.pop(form.get("code", ""), None)
        if issued is None or form.get("redirect_uri") != issued["redirect_uri"]:
            return httpx2.Response(400, json={"error": "invalid_grant"})
        verifier = form.get("code_verifier", "")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        if challenge.rstrip(b"=").decode() != issued["code_challenge"]:
            return httpx2.Response(400, json={"error": "invalid_grant"})
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "sub": self.subject,
            "aud": CLIENT_ID,
            "iat": now,
            "exp": now + 300,
            "nonce": issued["nonce"],
            "name": self.name,
            **self.overrides,
        }
        id_token = jwt.encode({"alg": "RS256", "kid": "k1"}, claims, self.signing_key)
        self.last_id_token = id_token
        return httpx2.Response(
            200,
            json={
                "access_token": "access",
                "token_type": "Bearer",
                "expires_in": 300,
                "id_token": id_token,
            },
        )


def _settings(**changes: Any) -> Settings:
    values: dict[str, Any] = {
        "oidc_issuer": ISSUER,
        "oidc_client_id": CLIENT_ID,
        "oidc_client_secret": CLIENT_SECRET,
        "session_secret": "test-session-secret",
        "public_url": None,
    }
    return Settings(**{**values, **changes})


async def _start(client: httpx2.AsyncClient, broker: FakeBroker) -> tuple[str, str]:
    response = await client.get("/api/auth/login")
    assert response.status_code == 302
    return broker.approve(response.headers["location"])


async def _sign_in(client: httpx2.AsyncClient, broker: FakeBroker) -> httpx2.Response:
    code, state = await _start(client, broker)
    return await client.get("/api/auth/callback", params={"code": code, "state": state})


async def _count(adb: AsyncSession, table: str) -> int:
    return await adb.scalar(text(f"SELECT count(*) FROM {table}"))


def _session_cookie(response: httpx2.Response) -> str:
    """The session cookie's own Set-Cookie header, lowercased. The callback
    also clears the sign-in cookie, whose attributes must not stand in."""
    (header,) = [
        h for h in response.headers.get_list("set-cookie") if h.startswith(f"{SESSION_COOKIE}=")
    ]
    return header.lower()


def _failed(response: httpx2.Response) -> bool:
    return (
        response.status_code == 303
        and response.headers["location"] == "/?sign-in=failed"
        and SESSION_COOKIE not in response.cookies
    )
