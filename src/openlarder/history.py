"""Edit history (migration 0040): telling the database who is writing, and
reading what it recorded. *Ray, 2026-11-10: every catalog change.*

The trigger reads three settings, local to each transaction: who
(openlarder.actor), which change (openlarder.change, one per request so a
save reads as one change however many rows it touched), and what it came
through (openlarder.via: an import run, an accepted suggestion). They're
set when a transaction begins, from context variables a middleware resets
for every request; current_user sets the actor as soon as it knows it,
since its own query has begun the transaction by then.

Who may read a revision follows visibility.py: anything in a family
collection only while the collection exists and the reader can see it, and
an ingredient's or author's only while it's one the reader can see.
"""

import uuid
from contextvars import ContextVar

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as OrmSession

_actor: ContextVar[uuid.UUID | None] = ContextVar("history_actor", default=None)
_change: ContextVar[uuid.UUID | None] = ContextVar("history_change", default=None)
_via: ContextVar[str | None] = ContextVar("history_via", default=None)

_SET = text(
    "SELECT set_config('openlarder.actor', :actor, true),"
    " set_config('openlarder.change', :change, true),"
    " set_config('openlarder.via', :via, true)"
)


def _params() -> dict[str, str]:
    actor, change = _actor.get(), _change.get()
    return {
        "actor": str(actor) if actor else "",
        # Outside a request (work after the response), one per transaction.
        "change": str(change or uuid.uuid4()),
        "via": _via.get() or "",
    }


@event.listens_for(OrmSession, "after_begin")
def _stamp(session, transaction, connection) -> None:
    connection.execute(_SET, _params())


class Middleware:
    """A fresh change, and no one yet, for each request."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        tokens = (_actor.set(None), _change.set(uuid.uuid4()), _via.set(None))
        try:
            await self.app(scope, receive, send)
        finally:
            _actor.reset(tokens[0])
            _change.reset(tokens[1])
            _via.reset(tokens[2])


async def _restamp(session: AsyncSession) -> None:
    if session.in_transaction():
        await session.execute(_SET, _params())


async def acting(session: AsyncSession, user_id: uuid.UUID | None) -> None:
    """Who is writing, from now on in this request."""
    _actor.set(user_id)
    await _restamp(session)


async def via(session: AsyncSession, what: str | None) -> None:
    """What the writes from now on come through ("import:<run id>")."""
    _via.set(what)
    await _restamp(session)
