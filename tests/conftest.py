"""Test database setup.

The suite runs against a real Postgres, because what it tests -- constraints,
composite keys, the effective-tags view -- lives in the database. It creates a
throwaway database beside the configured one, migrates it with the real
migration, and drops it at the end.
"""

import asyncio
import hashlib
import os
import selectors
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from fake_archive import FakeArchive
from fake_broker import CLIENT_ID, CLIENT_SECRET, ISSUER, FakeBroker, _settings
from fake_openlibrary import FakeOpenLibrary
from fake_wikidata import FakeWikidata
from openlarder.archiving import Archiver, get_archiver
from openlarder.auth import SESSION_COOKIE, build_oidc_client, optional_oidc_client
from openlarder.config import Settings, get_settings
from openlarder.db import get_session
from openlarder.main import app
from openlarder.routers.authors import wikidata_transport
from openlarder.routers.sources import openlibrary_transport

if sys.platform == "win32":
    # Psycopg's async mode refuses Windows' default proactor loop. Linux, where
    # CI and production run, needs nothing, so the hook exists only here.
    def pytest_asyncio_loop_factories(config, item):
        return {"selector": lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())}


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    base = make_url(get_settings().database_url)
    name = f"openlarder_test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
        # A query that never ends dies in Postgres, not just in pytest: on
        # 2026-11-08 a deliberately broken recursive query outlived its killed
        # test and wrote 350 GB of temp files before anyone noticed.
        conn.execute(text(f"ALTER DATABASE \"{name}\" SET statement_timeout = '60s'"))
        conn.execute(text(f"ALTER DATABASE \"{name}\" SET temp_file_limit = '1GB'"))
    url = base.set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Iterator[Config]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    previous = os.environ.get("OPENLARDER_DATABASE_URL")
    os.environ["OPENLARDER_DATABASE_URL"] = database_url
    get_settings.cache_clear()
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    try:
        yield cfg
    finally:
        if previous is None:
            os.environ.pop("OPENLARDER_DATABASE_URL", None)
        else:
            os.environ["OPENLARDER_DATABASE_URL"] = previous
        get_settings.cache_clear()


@pytest.fixture(scope="session")
def engine(database_url: str, alembic_config: Config) -> Iterator[Engine]:
    command.upgrade(alembic_config, "head")
    eng = create_engine(database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Connection]:
    """A connection whose work is rolled back after each test."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


# Signing in, through the fake broker in fake_broker.py.


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


@pytest.fixture
def ia(monkeypatch) -> FakeArchive:
    """The Internet Archive every test gets: a fake, so nothing reaches the
    real one, refusing everything unless the test says otherwise."""
    from openlarder import archive

    monkeypatch.setattr(archive, "POLL_EVERY", 0.0)
    return FakeArchive()


@pytest.fixture
def configure(adb: AsyncSession, broker: FakeBroker, ia: FakeArchive) -> Iterator[Any]:
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

    # Archiving after the response uses the test's session, and the fake.
    @asynccontextmanager
    async def same_session() -> AsyncIterator[AsyncSession]:
        yield adb

    app.dependency_overrides[get_archiver] = lambda: Archiver(
        same_session, None, httpx2.MockTransport(ia.handle)
    )
    apply(_settings())
    try:
        yield apply
    finally:
        app.dependency_overrides.clear()


# The header a browser adds to a page's requests to its own site: tests act
# as the site, which the API's rate limit leaves alone (ratelimit.py).
AS_THE_SITE = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    from openlarder import ratelimit, usage
    from openlarder.routers import book_requests

    ratelimit.reset()
    usage.reset()
    book_requests.reset()


@pytest.fixture
async def client(configure) -> AsyncIterator[httpx2.AsyncClient]:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://testserver",
        headers=AS_THE_SITE,
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _open_library_unpaced(monkeypatch):
    """The fake Open Library needs no pacing; test_books tests the pacing itself."""
    from openlarder import openlibrary

    monkeypatch.setattr(openlibrary, "MIN_INTERVAL", 0.0)


@pytest.fixture
def openlib(configure) -> FakeOpenLibrary:
    fake = FakeOpenLibrary()
    app.dependency_overrides[openlibrary_transport] = lambda: httpx2.MockTransport(fake.handle)
    return fake


@pytest.fixture
def wikidata(configure, monkeypatch) -> FakeWikidata:
    from openlarder import wikidata as client

    monkeypatch.setattr(client, "MIN_INTERVAL", 0.0)
    fake = FakeWikidata()
    app.dependency_overrides[wikidata_transport] = lambda: httpx2.MockTransport(fake.handle)
    return fake


@pytest.fixture
async def people(client, adb):
    """Clients signed in as different people: people("ann", admin=True)."""
    async with AsyncExitStack() as stack:

        async def person(name: str, admin: bool = False) -> httpx2.AsyncClient:
            token = f"token-{name}-{uuid.uuid4().hex}"
            await adb.execute(
                text(
                    "WITH u AS (INSERT INTO users (issuer, subject, display_name, is_admin)"
                    " VALUES ('test', :n, :n, :a) RETURNING id)"
                    " INSERT INTO user_sessions (user_id, token_hash, expires_at)"
                    " SELECT id, :h, now() + interval '1 day' FROM u"
                ),
                {"n": name, "a": admin, "h": hashlib.sha256(token.encode()).digest()},
            )
            c = await stack.enter_async_context(
                httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app),
                    base_url="http://testserver",
                    cookies={SESSION_COOKIE: token},
                    headers=AS_THE_SITE,
                )
            )
            return c

        yield person
