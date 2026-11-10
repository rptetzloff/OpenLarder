"""Trusted contributors: what they add publishes without review. *Ray,
2026-11-10.*

Earned by "the greater of 250 recipes or 5 books": at least
OPENLARDER_TRUST_RECIPES of their recipes approved by a moderator, across at
least OPENLARDER_TRUST_BOOKS different sources, both. It's looked at each
time a moderator approves something of theirs. A moderator can also grant
it by hand, or withhold it; withheld sticks, so it isn't earned straight
back. A trusted contributor's additions are still in the edit history and
can be undone; changes to records already published still go through
proposals (routers/proposals.py).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.config import Settings
from openlarder.models import Recipe, User


@dataclass
class Progress:
    trusted: bool
    trust: str | None
    recipes: int
    books: int
    needs_recipes: int
    needs_books: int


async def progress(session: AsyncSession, user: User, settings: Settings) -> Progress:
    """How far they are: their recipes a moderator approved, and in how many
    sources."""
    approved = (
        Recipe.created_by == user.id,
        Recipe.review == "published",
        Recipe.reviewed_at.is_not(None),
    )
    recipes = await session.scalar(select(func.count()).where(*approved)) or 0
    books = (
        await session.scalar(select(func.count(func.distinct(Recipe.source_id))).where(*approved))
        or 0
    )
    return Progress(
        trusted=user.trusted,
        trust=user.trust,
        recipes=recipes,
        books=books,
        needs_recipes=settings.trust_recipes,
        needs_books=settings.trust_books,
    )


async def consider(session: AsyncSession, user_id: uuid.UUID | None, settings: Settings) -> bool:
    """After an approval: trust a contributor who's now earned it. Whether
    they were made trusted."""
    if user_id is None:
        return False
    user = await session.get(User, user_id)
    if user is None or user.trust is not None or user.may_edit or not user.may_claim:
        return False
    found = await progress(session, user, settings)
    if found.recipes >= settings.trust_recipes and found.books >= settings.trust_books:
        user.trust, user.trust_set_at, user.trust_set_by = "earned", func.now(), None
        return True
    return False
