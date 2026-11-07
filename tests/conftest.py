"""Test database setup.

The suite runs against a real Postgres, because what it tests -- constraints,
composite keys, the effective-tags view -- lives in the database. It creates a
throwaway database beside the configured one, migrates it with the real
migration, and drops it at the end.
"""

import asyncio
import os
import selectors
import sys
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url

from openlarder.config import get_settings

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
