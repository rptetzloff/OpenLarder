"""The database engine and the session dependency."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from openlarder.config import get_settings

# Postgres compiles a query it estimates as costly (JIT) before running it.
# For this app's queries that only costs: a search by ingredient on a
# production-sized catalog spent 290 ms compiling and 98 ms running. Off
# for every connection the app makes, so nothing depends on the server's
# settings.
CONNECT_ARGS = {"options": "-c jit=off"}

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.database_echo,
            pool_pre_ping=True,
            connect_args=CONNECT_ARGS,
        )
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Sessions outside a request, as for work done after the response."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


Session = Annotated[AsyncSession, Depends(get_session)]
