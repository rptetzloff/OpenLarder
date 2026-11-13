"""Book titles that look to be in the wrong capitals, or to have lost an
apostrophe: suggestions for a moderator, never a change made unasked.

*Ray's round 2 spec, 2026-11-13.* Titles that arrived in a catalogue's
sentence case ("The grilling book") sit beside title-case ones, and one
had lost its apostrophe ("Danielle Walkers Healthy in a Hurry"). Nothing
is recapitalised when it's shown: some titles are styled on purpose, and a
rule can't tell which. So each goes to the Suggestions queue (routers/
suggestions.py), where a moderator accepts it, which changes the title as
an edit of theirs, or dismisses it, after which the same change isn't
suggested for that book again.

**Capitals** (kind ``title_case``): a title is looked at when a word after
its first is four letters or more and all lower case, as the spec has it.
What's suggested capitalises every word that is all lower case, except a
SMALL one that doesn't begin the title or the part after a colon or dash.
A word with a capital anywhere in it is left as written ("BBQ", "iPad",
"McGee"). If that changes nothing, nothing is suggested: SMALL has "with",
"from" and the other short prepositions titles leave small, beyond the
spec's examples, so a book printed "Cooking with Fire" isn't offered
"Cooking With Fire".

**A lost apostrophe** (kind ``title_apostrophe``): a word ending in "s"
whose rest is a name of one of the book's authors, straight before a
capitalised word: "Walkers" on a book by Danielle Walker. The spec called
this a flag. Flags hang on recipes (models/flags.py), and a suggestion
carries the corrected title, so it's one of these instead.

Books only, and only those anyone can see: a private collection's title
never reaches the queue, and a website's or a magazine's name is often
lower case on purpose.

What these can't see: a title run together ("Everydaycook"); a title in
another language, where sentence case is right and the suggestion is
simply dismissed; a possessive of a name that isn't an author's.
"""

import re
import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import visibility
from openlarder.models import Author, Source, SourceCredit, Suggestion

MODEL = "rules"
VERSION = "title-rules-v1"
CASE = "title_case"
APOSTROPHE = "title_apostrophe"
KINDS = (CASE, APOSTROPHE)

# Left small in a title unless they begin it: articles, conjunctions and
# the short prepositions.
SMALL = frozenset(
    "a an the and but or nor for so yet as at by in of on to up via per vs"
    " with from into onto over than".split()
)

# Letters, with an apostrophe inside ("cook's") if there is one.
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
# What a new part of a title follows: "Jerusalem: a cookbook".
_BREAK = re.compile(r"[:—–]|\s-\s")


def _words(title: str) -> list[tuple[re.Match[str], bool]]:
    """Each word and whether it begins the title or a part of it. A word
    straight after a digit isn't one: the "nd" of "2nd"."""
    found = []
    end = 0
    for match in WORD.finditer(title):
        if match.start() and title[match.start() - 1].isdigit():
            continue
        begins = not found or bool(_BREAK.search(title[end : match.start()]))
        found.append((match, begins))
        end = match.end()
    return found


def _lower(word: str) -> bool:
    return word.replace("'", "").replace("’", "").islower()


def in_title_case(title: str) -> str | None:
    """The title in title case, if it looks to be in sentence case; None if
    it doesn't, or if that would change nothing."""
    words = _words(title)
    if not any(_lower(m.group()) and len(m.group()) >= 4 for m, _ in words[1:]):
        return None
    out, at = [], 0
    for match, begins in words:
        word = match.group()
        out.append(title[at : match.start()])
        keep = not _lower(word) or (word in SMALL and not begins)
        out.append(word if keep else word[0].upper() + word[1:])
        at = match.end()
    out.append(title[at:])
    cased = "".join(out)
    return cased if cased != title else None


def with_apostrophe(title: str, authors: Iterable[str]) -> str | None:
    """The title with the apostrophe an author's name looks to have lost,
    or None: "Danielle Walkers Healthy in a Hurry", by Danielle Walker."""
    names = {part.casefold() for name in authors for part in WORD.findall(name) if len(part) >= 3}
    words = [m for m, _ in _words(title)]
    mark = "’" if "’" in title else "'"
    for here, after in zip(words, words[1:], strict=False):
        word = here.group()
        if (
            word.endswith("s")
            and "'" not in word
            and "’" not in word
            and word[:-1].casefold() in names
            # "Williams" by Chris Williams is the name itself.
            and word.casefold() not in names
            and after.group()[0].isupper()
            and title[here.end() : after.start()].isspace()
        ):
            return title[: here.end() - 1] + mark + "s" + title[here.end() :]
    return None


def _reason(kind: str) -> str:
    if kind == CASE:
        return "The title looks to be in sentence case."
    return "A word of the title is an author's name with an “s” and no apostrophe."


async def sweep(session: AsyncSession, only: Sequence[uuid.UUID] | None = None) -> int:
    """Add a suggestion for each public book's title these rules would
    change (only: just these sources); how many were new. A change already
    accepted or dismissed for a book isn't suggested again. The caller
    commits."""
    books = select(Source.id, Source.title).where(
        Source.kind == "book", visibility.sources_seen_by(None)
    )
    if only is not None:
        books = books.where(Source.id.in_(only))
    titles = dict((await session.execute(books)).all())
    if not titles:
        return 0
    credited: dict[uuid.UUID, list[str]] = {}
    for source_id, as_printed, name in await session.execute(
        select(SourceCredit.source_id, SourceCredit.credited_as, Author.name)
        .join(Author, Author.id == SourceCredit.author_id)
        .where(SourceCredit.source_id.in_(titles))
    ):
        credited.setdefault(source_id, []).extend(n for n in (as_printed, name) if n)
    decided = {
        (kind, p.get("source_id"), p.get("title"))
        for kind, p in await session.execute(
            select(Suggestion.kind, Suggestion.proposal).where(
                Suggestion.kind.in_(KINDS), Suggestion.status != "open"
            )
        )
        if isinstance(p, dict)
    }
    new = 0
    for source_id, title in titles.items():
        for kind, proposed in (
            (CASE, in_title_case(title)),
            (APOSTROPHE, with_apostrophe(title, credited.get(source_id, ()))),
        ):
            if proposed is None or (kind, str(source_id), proposed) in decided:
                continue
            result = await session.execute(
                insert(Suggestion)
                .values(
                    kind=kind,
                    target={"source_id": str(source_id)},
                    proposal={"source_id": str(source_id), "title_now": title, "title": proposed},
                    reason=_reason(kind),
                    model=MODEL,
                    prompt_version=VERSION,
                )
                .on_conflict_do_nothing(
                    index_elements=["kind", "target"], index_where=text("status = 'open'")
                )
                .returning(Suggestion.id)
            )
            new += result.scalar() is not None
    return new
