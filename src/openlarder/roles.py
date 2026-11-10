"""Who may do what: a ladder of roles. *Ray, 2026-11-10.*

- user: anyone signed in. Their own family collections, groups, flags on
  what they added, requests and votes.
- contributor: claims book requests and queues them up. Adding to the
  catalog, held for review, comes with the review queue (TODO.md,
  Contributions).
- moderator: edits the catalog directly: sources, recipes, authors,
  ingredients, tags, merges; works the flags and suggestions; declines
  requests; makes people contributors.
- admin: runs the site: bulk imports, API usage and keys, buy-link clicks;
  makes people moderators.
- owner: makes people admins. Set only in the database, never from the
  site, so no page can hand it over:

      UPDATE users SET role = 'owner' WHERE display_name = '...';

Each role can do everything below it. Granting is by rank: someone may
give or take away a role only below their own, and can't change their own.
"""

from typing import Literal

Role = Literal["user", "contributor", "moderator", "admin", "owner"]
LADDER: tuple[Role, ...] = ("user", "contributor", "moderator", "admin", "owner")
LABELS: dict[str, str] = {
    "user": "User",
    "contributor": "Contributor",
    "moderator": "Moderator",
    "admin": "Administrator",
    "owner": "Owner",
}


def rank(role: str) -> int:
    return LADDER.index(role)  # type: ignore[arg-type]


def at_least(role: str, needed: Role) -> bool:
    return rank(role) >= rank(needed)


def grantable(role: str) -> list[Role]:
    """The roles someone with this role may give or take away: those below
    their own, from moderator up (a moderator makes contributors)."""
    if not at_least(role, "moderator"):
        return []
    return [r for r in LADDER if rank(r) < rank(role)]
