"""Daily allowances, counted in the database (models/limits.py): one
statement adds one to today's count unless it's at the limit, so two app
processes, or two requests at once, can't both take the last one. Days run
midnight to midnight UTC."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_TODAY = "(now() AT TIME ZONE 'UTC')::date"


async def take(session: AsyncSession, what: str, caller: str, limit: int) -> bool:
    """One of the caller's allowance for today, if any is left. Committed at
    once: an attempt that fails afterwards still counts, as it cost work."""
    await session.execute(text(f"DELETE FROM daily_counts WHERE day < {_TODAY}"))
    taken = await session.scalar(
        text(
            f"INSERT INTO daily_counts (day, what, caller, n) VALUES ({_TODAY}, :what, :caller, 1)"
            " ON CONFLICT (day, what, caller) DO UPDATE SET n = daily_counts.n + 1"
            " WHERE daily_counts.n < :limit"
            " RETURNING n"
        ),
        {"what": what, "caller": caller, "limit": limit},
    )
    await session.commit()
    return taken is not None
