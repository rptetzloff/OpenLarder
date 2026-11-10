"""The contributor agreement: accepted once before adding to the catalog,
and again when its version changes. *Ray, 2026-11-10: everyone who adds,
the owner included.* SCOPING.md: the catalog is open data under the ODbL,
and contributors agree to it before their first contribution.

The wording is the site's, not a lawyer's yet: the lawyer review planned
for the terms and the content rules covers it too (SCOPING.md, Before
launch). Changing what it says means a new VERSION, which asks everyone
again: 2026-11-10.2 said that trusted contributors' additions don't wait.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status

from openlarder.auth import CurrentUser
from openlarder.models import User

VERSION = "2026-11-10.2"

POINTS = [
    "What you add to OpenLarder's catalog (sources, recipes' titles and where they are, "
    "ingredient names, and changes to any of them) is open data under the Open Database "
    "License (ODbL) 1.0. You license what you add under the ODbL, so anyone may use, share "
    "and build on it, crediting OpenLarder and keeping what they build open.",
    "Add facts only: where a recipe is and what goes in it, by name. Never amounts, the "
    "method, photographs, or text copied from a book, site or show.",
    "Add only what you're free to share: nothing from a source whose terms forbid copying "
    "its index or data.",
    "Your display name is shown beside what you add and change, in the edit history, for "
    "anyone to read.",
    "What you add waits for a moderator's review before it's public, until you're a trusted "
    "contributor; moderators may change anything you add, send it back to you with a "
    "reason, or remove it.",
]


def has_agreed(user: User) -> bool:
    return user.agreed_version == VERSION


async def require_agreement(user: CurrentUser) -> User:
    if not has_agreed(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Accept the contributor agreement first: it's on your account page.",
        )
    return user


Agreed = Annotated[User, Depends(require_agreement)]


async def require_contributing(user: CurrentUser) -> User:
    """Adds books and recipes to the catalog: a contributor or above, who
    has accepted the agreement. A contributor's waits for review."""
    if not user.may_claim:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only contributors can add to the catalog yet. A moderator can make you one.",
        )
    return await require_agreement(user)


Contributing = Annotated[User, Depends(require_contributing)]
