"""Linking a book already here to its Open Library record (issue #32).

A book added without an Open Library match has no work ID, so a later
Open Library ISBN for it would arrive as a second book. Linking sets the
work ID, brings in Open Library's edition, and ties the credited authors to
Open Library's author records. What is here already wins: titles and
credits are not rewritten, and an edition only has its blanks filled.

plan() works out what linking would do without writing anything, so the
admin can check the Open Library record is the same book first; several
"Heritage Cookbook"s by other authors exist there. apply() does it.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass, field

from sqlalchemy import false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.models import Author, Edition, Source, SourceCredit
from openlarder.openlibrary import FoundAuthor, FoundBook


@dataclass
class AuthorStep:
    found: FoundAuthor
    # "linked": already tied to this record; "link": the credit named
    # credited_as gets tied to it; "add": credited, as the book had no
    # credits; "unmatched": no credit here has this name, so it is left off.
    outcome: str
    credit: SourceCredit | None = None


@dataclass
class Plan:
    found: FoundBook
    problem: str | None = None
    # "fill": edition is this book's copy of Open Library's edition;
    # "add": it becomes another edition; None: a work alone, no edition.
    edition_step: str | None = None
    edition: Edition | None = None
    authors: list[AuthorStep] = field(default_factory=list)


def name_key(name: str) -> str:
    """A name reduced for matching: "Moore, Russell (Chef)" -> "russell moore".

    Bracketed notes go, "Last, First" turns round, and accents, case and
    punctuation are ignored. Only for comparing; nothing stores it.
    """
    name = re.sub(r"\([^)]*\)", " ", name)
    if name.count(",") == 1:
        last, first = name.split(",")
        name = f"{first} {last}"
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", name.casefold()).split())


async def plan(session: AsyncSession, work: Source, found: FoundBook) -> Plan:
    result = Plan(found=found)
    if not found.open_library_work_id:
        result.problem = (
            "Open Library has that edition without a work, so there's nothing to link the book to."
        )
        return result
    if work.open_library_work_id and work.open_library_work_id != found.open_library_work_id:
        result.problem = (
            f"This book is already linked to another Open Library work, "
            f"{work.open_library_work_id}."
        )
        return result
    other = await session.scalar(
        select(Source).where(
            Source.open_library_work_id == found.open_library_work_id, Source.id != work.id
        )
    )
    if other is not None:
        result.problem = (
            f"That Open Library work is already another book here, “{other.title}”. "
            "Linking would make them one book, which needs a merge."
        )
        return result

    if found.edition_id:
        matches = (
            await session.scalars(
                select(Edition).where(
                    (Edition.open_library_edition_id == found.edition_id)
                    | ((Edition.isbn13 == found.isbn13) if found.isbn13 else false())
                )
            )
        ).all()
        elsewhere = [e for e in matches if e.source_id != work.id]
        if elsewhere:
            book = await session.get(Source, elsewhere[0].source_id)
            result.problem = (
                f"That edition is already in another book here, “{book.title if book else '?'}”."
            )
            return result
        if len(matches) > 1:
            # Its ISBN on one edition here and its Open Library ID on another.
            result.problem = "That edition matches two editions of this book. Fix them first."
            return result
        result.edition_step = "fill" if matches else "add"
        result.edition = matches[0] if matches else None

    credits = (
        await session.execute(
            select(SourceCredit, Author)
            .join(Author, Author.id == SourceCredit.author_id)
            .where(SourceCredit.source_id == work.id)
            .order_by(SourceCredit.position)
        )
    ).all()
    taken: set[uuid.UUID] = set()
    for found_author in found.authors:
        step = AuthorStep(found_author, "unmatched")
        for credit, author in credits:
            if author.open_library_author_id == found_author.open_library_id:
                step = AuthorStep(found_author, "linked", credit)
                break
        else:
            key = name_key(found_author.name)
            for credit, author in credits:
                if (
                    credit.id not in taken
                    and author.open_library_author_id is None
                    and key in (name_key(credit.credited_as), name_key(author.name))
                ):
                    step = AuthorStep(found_author, "link", credit)
                    break
            else:
                if not credits:
                    step = AuthorStep(found_author, "add")
        if step.credit is not None:
            taken.add(step.credit.id)
        result.authors.append(step)
    return result


async def apply(session: AsyncSession, work: Source, steps: Plan) -> None:
    """Carry out a plan with no problem."""
    assert steps.problem is None
    found = steps.found
    work.open_library_work_id = found.open_library_work_id

    if steps.edition_step == "fill" and steps.edition is not None:
        edition = steps.edition
        edition.open_library_edition_id = found.edition_id
        edition.isbn13 = edition.isbn13 or found.isbn13
        edition.publisher = edition.publisher or found.publisher
        edition.published_year = edition.published_year or found.published_year
        edition.open_library_cover_id = edition.open_library_cover_id or found.cover_id
    elif steps.edition_step == "add":
        session.add(
            Edition(
                source_id=work.id,
                title=(
                    found.edition_title
                    if found.edition_title
                    and found.edition_title.casefold() != work.title.casefold()
                    else None
                ),
                isbn13=found.isbn13,
                publisher=found.publisher,
                published_year=found.published_year,
                open_library_edition_id=found.edition_id,
                open_library_cover_id=found.cover_id,
            )
        )

    position = 0
    for step in steps.authors:
        if step.outcome not in ("link", "add"):
            continue
        known = await session.scalar(
            select(Author).where(Author.open_library_author_id == step.found.open_library_id)
        )
        if step.outcome == "add":
            if known is None:
                known = Author(
                    name=step.found.name,
                    kind=step.found.kind,
                    open_library_author_id=step.found.open_library_id,
                )
                session.add(known)
                await session.flush()
            position += 1
            session.add(
                SourceCredit(
                    source_id=work.id,
                    author_id=known.id,
                    position=position,
                    credited_as=step.found.name,
                )
            )
            continue
        credit = step.credit
        assert credit is not None
        if known is None:
            # This book's author record is Open Library's author: tie them.
            author = await session.get(Author, credit.author_id)
            assert author is not None
            author.open_library_author_id = step.found.open_library_id
            continue
        # Open Library's author is already here, from another book: point the
        # credit at that record, and drop this one if nothing else uses it.
        old = credit.author_id
        credit.author_id = known.id
        await session.flush()
        still_used = await session.scalar(
            select(func.count()).select_from(SourceCredit).where(SourceCredit.author_id == old)
        )
        if not still_used:
            orphan = await session.get(Author, old)
            if orphan is not None and orphan.open_library_author_id is None:
                await session.delete(orphan)
    await session.flush()
