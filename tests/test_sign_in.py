"""Sign-in, against a fake broker and the real database.

The broker is faked at the HTTP layer, below Authlib: it publishes discovery
metadata and a key set, and its token endpoint checks the client secret, the
PKCE verifier and the redirect URI before handing back an RS256 ID token. So
these tests exercise Authlib's real checks and the app's real routes; what
they cannot show is that Authentik behaves like the fake. That is checked by
signing in on the deployed site.
"""

import base64
import hashlib
import secrets
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from alembic import command
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey
from pydantic import ValidationError
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from openlarder.auth import SESSION_COOKIE, build_oidc_client, hash_token, optional_oidc_client
from openlarder.config import Settings, get_settings
from openlarder.db import get_session
from openlarder.main import app

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


@pytest.fixture(scope="session")
async def async_engine(database_url: str, engine) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(database_url)
    yield eng
    await eng.dispose()


@pytest.fixture
async def adb(async_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session whose commits land in a savepoint and are rolled back after the test."""
    async with async_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest.fixture
def broker() -> FakeBroker:
    return FakeBroker()


def _settings(**changes: Any) -> Settings:
    values: dict[str, Any] = {
        "oidc_issuer": ISSUER,
        "oidc_client_id": CLIENT_ID,
        "oidc_client_secret": CLIENT_SECRET,
        "session_secret": "test-session-secret",
        "public_url": None,
    }
    return Settings(**{**values, **changes})


@pytest.fixture
def configure(adb: AsyncSession, broker: FakeBroker) -> Iterator[Any]:
    def apply(settings: Settings) -> None:
        app.dependency_overrides[get_settings] = lambda: settings
        if settings.sign_in_configured:
            # Built once per configuration, as in production, so the metadata
            # and keys are fetched once.
            client = build_oidc_client(
                ISSUER, CLIENT_ID, CLIENT_SECRET, httpx2.MockTransport(broker.handle)
            )
            app.dependency_overrides[optional_oidc_client] = lambda: client
        else:
            app.dependency_overrides.pop(optional_oidc_client, None)

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield adb

    app.dependency_overrides[get_session] = session_override
    apply(_settings())
    try:
        yield apply
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def client(configure) -> AsyncIterator[httpx2.AsyncClient]:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


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


async def test_sign_in_creates_a_user_and_a_session(client, broker, adb) -> None:
    response = await _sign_in(client, broker)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = _session_cookie(response)
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["display_name"] == "Test Cook"
    row = (await adb.execute(text("SELECT issuer, subject FROM users"))).one()
    assert tuple(row) == (ISSUER, "subject-1")


async def test_login_asks_for_pkce_a_nonce_and_the_callback(client) -> None:
    response = await client.get("/api/auth/login")
    query = {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}

    assert query["response_type"] == "code"
    assert query["client_id"] == CLIENT_ID
    assert "openid" in query["scope"].split()
    assert query["code_challenge_method"] == "S256"
    assert query["code_challenge"] and query["nonce"] and query["state"]
    assert query["redirect_uri"] == "http://testserver/api/auth/callback"


async def test_public_url_sets_the_callback_and_secure_cookies(client, broker, configure) -> None:
    configure(_settings(public_url="https://openlarder.test/"))
    login = await client.get("/api/auth/login")
    query = parse_qs(urlsplit(login.headers["location"]).query)
    assert query["redirect_uri"] == ["https://openlarder.test/api/auth/callback"]

    code, state = broker.approve(login.headers["location"])
    response = await client.get("/api/auth/callback", params={"code": code, "state": state})
    assert "secure" in _session_cookie(response)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"nonce": "not-the-one-sent"}, id="nonce"),
        pytest.param({"aud": "some-other-app"}, id="audience"),
        pytest.param({"iss": "https://elsewhere.test/"}, id="issuer"),
        # Past Authlib's two minutes of leeway for clock skew.
        pytest.param({"exp": int(time.time()) - 600, "iat": int(time.time()) - 900}, id="expired"),
        pytest.param({"sub": ""}, id="no-subject"),
    ],
)
async def test_an_id_token_that_fails_a_check_is_refused(client, broker, adb, overrides) -> None:
    broker.overrides = overrides
    assert _failed(await _sign_in(client, broker))
    assert await _count(adb, "users") == 0


async def test_a_broker_claiming_another_issuer_is_refused(client, broker, adb) -> None:
    """Discovery and token agree with each other, but not with the configured issuer."""
    broker.issuer = "https://impostor.test/"
    assert _failed(await _sign_in(client, broker))
    assert await _count(adb, "users") == 0


async def test_an_id_token_signed_by_another_key_is_refused(client, broker, adb) -> None:
    broker.signing_key = RSAKey.generate_key(2048, parameters={"kid": "k1"})
    assert _failed(await _sign_in(client, broker))
    assert await _count(adb, "users") == 0


async def test_a_forged_state_is_refused_before_the_code_is_spent(client, broker) -> None:
    code, _ = await _start(client, broker)
    response = await client.get("/api/auth/callback", params={"code": code, "state": "forged"})
    assert _failed(response)
    assert broker.token_requests == 0


async def test_a_state_works_once(client, broker) -> None:
    login = await client.get("/api/auth/login")
    code, state = broker.approve(login.headers["location"])
    assert (await client.get("/api/auth/callback", params={"code": code, "state": state})).headers[
        "location"
    ] == "/"

    # A fresh code for the same request, so only the spent state can refuse it.
    again, _ = broker.approve(login.headers["location"])
    response = await client.get("/api/auth/callback", params={"code": again, "state": state})
    assert _failed(response)
    assert broker.token_requests == 1


async def test_a_broker_error_is_refused(client, broker) -> None:
    _, state = await _start(client, broker)
    response = await client.get(
        "/api/auth/callback", params={"error": "access_denied", "state": state}
    )
    assert _failed(response)


async def test_signing_in_again_is_the_same_user(client, broker, adb) -> None:
    await _sign_in(client, broker)
    broker.name = "Renamed Cook"
    await _sign_in(client, broker)

    assert await _count(adb, "users") == 1
    assert await _count(adb, "user_sessions") == 2
    assert (await client.get("/api/auth/me")).json()["display_name"] == "Renamed Cook"


async def test_only_the_tokens_hash_is_stored(client, broker, adb) -> None:
    token = (await _sign_in(client, broker)).cookies[SESSION_COOKIE]
    stored = await adb.scalar(text("SELECT token_hash FROM user_sessions"))
    assert stored == hash_token(token)
    assert token.encode() not in stored


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


async def test_signing_out_ends_the_session(client, broker, adb) -> None:
    token = (await _sign_in(client, broker)).cookies[SESSION_COOKIE]
    response = await client.post("/api/auth/logout")

    assert response.status_code == 303
    assert await _count(adb, "user_sessions") == 0
    assert "max-age=0" in _session_cookie(response)
    # The old token is dead, not merely forgotten by this browser.
    client.cookies.set(SESSION_COOKIE, token)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_signing_out_goes_on_to_end_the_brokers_session(client, broker) -> None:
    await _sign_in(client, broker)
    location = (await client.post("/api/auth/logout")).headers["location"]

    assert location.startswith("https://broker.test/end-session/?")
    query = _query(location)
    # Authentik returns people only when the hint comes with the redirect.
    assert query["id_token_hint"] == broker.last_id_token
    assert query["post_logout_redirect_uri"] == "http://testserver/"


async def test_the_session_keeps_the_id_token_it_was_issued(client, broker, adb) -> None:
    await _sign_in(client, broker)
    assert await adb.scalar(text("SELECT id_token FROM user_sessions")) == broker.last_id_token


async def test_a_session_without_an_id_token_still_ends_at_the_broker(client, broker, adb) -> None:
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE user_sessions SET id_token = NULL"))
    location = (await client.post("/api/auth/logout")).headers["location"]

    assert location.startswith("https://broker.test/end-session/")
    # Without the hint the redirect would be refused, so it is not asked for.
    assert "post_logout_redirect_uri" not in _query(location)
    assert "id_token_hint" not in _query(location)


async def test_signing_out_with_no_session_goes_home(client) -> None:
    response = await client.post("/api/auth/logout")
    assert (response.status_code, response.headers["location"]) == (303, "/")
    client.cookies.set(SESSION_COOKIE, "made-up")
    response = await client.post("/api/auth/logout")
    assert (response.status_code, response.headers["location"]) == (303, "/")


async def test_signing_out_returns_to_the_public_url(broker, configure) -> None:
    configure(_settings(public_url="https://openlarder.test"))
    # https, because an https public URL makes the session cookie Secure and
    # a plain-http client would never send it back. And another host, as
    # behind the proxy, so the request alone cannot produce the right answer.
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="https://internal.test"
    ) as secure:
        await _sign_in(secure, broker)
        location = (await secure.post("/api/auth/logout")).headers["location"]
    assert _query(location)["post_logout_redirect_uri"] == "https://openlarder.test/"


async def test_without_a_broker_end_session_signing_out_still_ends_it_here(
    client, broker, adb
) -> None:
    broker.end_session = False
    await _sign_in(client, broker)
    response = await client.post("/api/auth/logout")

    assert (response.status_code, response.headers["location"]) == (303, "/")
    assert await _count(adb, "user_sessions") == 0


async def test_signing_out_with_sign_in_unconfigured_goes_home(client, configure) -> None:
    configure(Settings(oidc_issuer=None, oidc_client_id=None, oidc_client_secret=None))
    response = await client.post("/api/auth/logout")
    assert (response.status_code, response.headers["location"]) == (303, "/")


async def test_an_expired_session_is_not_signed_in(client, broker, adb) -> None:
    await _sign_in(client, broker)
    await adb.execute(
        text(
            "UPDATE user_sessions SET created_at = now() - interval '31 days',"
            " expires_at = now() - interval '1 day'"
        )
    )
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_signing_in_sweeps_that_users_expired_sessions(client, broker, adb) -> None:
    await _sign_in(client, broker)
    await adb.execute(
        text(
            "UPDATE user_sessions SET created_at = now() - interval '31 days',"
            " expires_at = now() - interval '1 day'"
        )
    )
    await _sign_in(client, broker)
    assert await _count(adb, "user_sessions") == 1


async def test_without_a_session_nobody_is_signed_in(client) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401
    client.cookies.set(SESSION_COOKIE, "made-up")
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_sign_in_unconfigured_says_so(client, configure) -> None:
    configure(Settings(oidc_issuer=None, oidc_client_id=None, oidc_client_secret=None))
    assert (await client.get("/api/auth/login")).status_code == 503


@pytest.mark.parametrize(
    "given, missing",
    [
        ({"oidc_issuer": ISSUER}, "OPENLARDER_OIDC_CLIENT_ID"),
        (
            {"oidc_issuer": ISSUER, "oidc_client_id": CLIENT_ID, "oidc_client_secret": "x"},
            "OPENLARDER_SESSION_SECRET",
        ),
        ({"oidc_client_secret": "x"}, "OPENLARDER_OIDC_ISSUER"),
    ],
)
def test_half_configured_sign_in_refuses_to_start(given, missing) -> None:
    with pytest.raises(ValidationError, match=missing):
        Settings(
            **{"oidc_issuer": None, "oidc_client_id": None, "oidc_client_secret": None, **given}
        )


def _user(db: Connection, subject: str = "s") -> Any:
    return db.execute(
        text("INSERT INTO users (issuer, subject, display_name) VALUES (:i, :s, 'n') RETURNING id"),
        {"i": ISSUER, "s": subject},
    ).scalar_one()


def _refused(db: Connection, sql: str, **params: Any) -> None:
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text(sql), params)


def test_one_user_per_identity(db: Connection) -> None:
    _user(db, "same")
    _refused(
        db,
        "INSERT INTO users (issuer, subject, display_name) VALUES (:i, 'same', 'other')",
        i=ISSUER,
    )


def test_a_session_stores_a_sha256_and_dies_with_its_user(db: Connection) -> None:
    user = _user(db)
    insert = (
        "INSERT INTO user_sessions (user_id, token_hash, expires_at)"
        " VALUES (:u, :h, now() + interval '1 day')"
    )
    _refused(db, insert, u=user, h=b"plain-token")
    _refused(
        db,
        "INSERT INTO user_sessions (user_id, token_hash, expires_at) VALUES (:u, :h, now())",
        u=user,
        h=hash_token("t"),
    )
    _refused(
        db,
        "INSERT INTO user_sessions (user_id, token_hash, expires_at, id_token)"
        " VALUES (:u, :h, now() + interval '1 day', '')",
        u=user,
        h=hash_token("t"),
    )
    db.execute(text(insert), {"u": user, "h": hash_token("t")})
    db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user})
    assert db.execute(text("SELECT count(*) FROM user_sessions")).scalar_one() == 0


def test_downgrade_refuses_while_users_exist(engine, alembic_config) -> None:
    with engine.begin() as conn:
        _user(conn, "downgrade-test")
    try:
        engine.dispose()
        with pytest.raises(RuntimeError, match="1 user"):
            command.downgrade(alembic_config, "0005")  # through 0007
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE subject = 'downgrade-test'"))
