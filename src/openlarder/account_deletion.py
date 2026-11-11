"""Deleting an account: what goes, what stays, and who a group passes to.

The privacy policy promises it: deleting an account removes the person's
user record, sessions, group memberships and family collections. Anything
private goes with them; what they gave the catalog under the contributor
agreement (ODbL) stays, no longer showing who.

- **Goes:** their family collections, with the edit history recorded for
  them (it holds what was in them); what they added that's still waiting
  for review, or was sent back, unless someone else has added to it; their
  open suggested changes; their votes on requests; and, through the
  database, their sessions, API keys, larder lists and group memberships.
- **Stays, without their name:** published books and recipes, requests
  they made, reports, and every other record that names who did it
  (ON DELETE SET NULL).
- **Groups:** one they were the last admin of passes to its longest-standing
  member, as admin; one with nobody left is deleted.
- **The owner** can't be deleted here: the owner is set in the database,
  and handing it on comes first.

Their Authgear account isn't touched: signing in again makes a new, empty
account here.
"""

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from openlarder import history
from openlarder.models import (
    Group,
    GroupMember,
    Proposal,
    Recipe,
    RequestVote,
    Revision,
    Source,
    User,
)


class Refused(Exception):
    """Why it can't be deleted, in words to show."""


async def delete_account(session: AsyncSession, user: User) -> None:
    if user.role == "owner":
        raise Refused(
            "The owner's account can't be deleted here: make someone else the owner first."
        )
    await history.via(session, "account-deletion")

    # Family collections, then the history recorded for them.
    collections = list(await session.scalars(select(Source.id).where(Source.owner_id == user.id)))
    if collections:
        await session.execute(delete(Source).where(Source.id.in_(collections)))
        await session.execute(
            delete(Revision).where(Revision.family, Revision.source_id.in_(collections))
        )

    # What's still waiting for review or was sent back, unless others have
    # added to it.
    await session.execute(
        delete(Recipe).where(Recipe.created_by == user.id, Recipe.review != "published")
    )
    others = aliased(Recipe)
    await session.execute(
        delete(Source).where(
            Source.created_by == user.id,
            Source.review != "published",
            ~exists().where(
                others.source_id == Source.id,
                func.coalesce(others.created_by != user.id, True),
            ),
        )
    )

    await session.execute(
        delete(Proposal).where(Proposal.proposed_by == user.id, Proposal.status == "open")
    )
    await session.execute(delete(RequestVote).where(RequestVote.voter == f"user:{user.id}"))

    # Groups they were the last admin of.
    theirs = list(
        await session.scalars(
            select(GroupMember.group_id).where(
                GroupMember.user_id == user.id, GroupMember.role == "admin"
            )
        )
    )
    for group_id in theirs:
        others_admin = await session.scalar(
            select(func.count()).where(
                GroupMember.group_id == group_id,
                GroupMember.role == "admin",
                GroupMember.user_id != user.id,
            )
        )
        if others_admin:
            continue
        heir = await session.scalar(
            select(GroupMember)
            .where(GroupMember.group_id == group_id, GroupMember.user_id != user.id)
            .order_by(GroupMember.created_at, GroupMember.user_id)
            .limit(1)
        )
        if heir is not None:
            heir.role = "admin"
        else:
            await session.execute(delete(Group).where(Group.id == group_id))

    await session.flush()
    await session.execute(delete(User).where(User.id == user.id))
    await session.flush()
