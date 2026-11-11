"""Reading an ingredient line: its options, and which recipe a page reference means.

A line is kept as the book names it ("Basic Cauli-Rice (p. 269), Noodles,
or Potato"). This reads its ranked options from it, and resolves an option
that cites a page to the recipe it means in the same book. Nothing here
touches the database; references.py stores what this works out.

Options are split only on "or". Commas split too, but only in a list that
ends ", or" ("A, B, or C", and each such list in "A or B, or C, D, or E"):
names carry commas of their own ("Lemon, Orange, and Grapefruit
Marmalade"). Nothing inside brackets is split.

A reference resolves, in order, to:
1. the recipe of that name on that page;
2. the recipe of that name on another page, flagged, as the index's rule
   for a wrong page says;
3. the one other recipe on that page, when the component is printed inside
   it ("Tomato Sauce (p. 114)" in the ravioli on page 114). *Ray,
   2026-11-07.* A component of the recipe itself stays unlinked;
4. on a page with several recipes, the one whose title shares the most
   words with the name: "Chicken Stock (p. 475)" on a page holding "Red Meat
   or Pork Stock" and "Chicken, Turkey, Duck, or Goose Stock". A tie stays
   unlinked. In the household index this links 675 more references, for
   96% of them;
5. nothing, flagged, when the book has no recipe on that page.
"""

import re
import uuid
from dataclasses import dataclass

from openlarder.models import FlagKind

# A page reference closing an option: "(p. 269)", "(pp. 12-13)", "(pg 6)".
# The closing bracket is optional: the index has a few "(p. 605" lines.
_REF = re.compile(
    r"\s*\((?:pp?|pg)\.?\s*([\dixvlc]+)(?:\s*[-–]\s*[\dixvlc]+)?\s*\)?\s*$", re.IGNORECASE
)
_OR = re.compile(r"\s+or\s+", re.IGNORECASE)
_COMMA = re.compile(r",\s*")


@dataclass(frozen=True)
class Option:
    name: str  # without its page reference
    page: str | None  # the page it cites, as written


def _top_level_split(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Split on pattern, but not inside brackets."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and (m := pattern.match(text, i)):
            parts.append(text[start:i])
            start = i = m.end()
            continue
        i += 1
    parts.append(text[start:])
    return parts


def _option(text: str) -> Option:
    found = _REF.search(text)
    # A bare "(p. 42)" names nothing, so it is kept as written, not as a page.
    if found and (name := text[: found.start()].strip()):
        return Option(name, found.group(1))
    return Option(text.strip(), None)


def options(line: str) -> list[Option]:
    """The line's options in the book's order; one for most lines."""
    parts = _top_level_split(line, _OR)
    split: list[str] = []
    for i, part in enumerate(parts):
        if i < len(parts) - 1 and part.rstrip().endswith(","):
            # "A, B, or C": the commas before an "or" separate options too,
            # before each "or" of a line with several: "Lamb Shank or
            # Shoulder, or Beef Shank, Shin, Cheek, or Chuck".
            split += _top_level_split(part.rstrip()[:-1], _COMMA)
        else:
            split.append(part)
    return [_option(p) for p in split if p.strip()]


@dataclass(frozen=True)
class BookRecipe:
    id: uuid.UUID
    title: str
    pages: frozenset[str]


@dataclass(frozen=True)
class Resolved:
    recipe_id: uuid.UUID | None
    flag: tuple[FlagKind, str] | None = None


def _pages(recipe: BookRecipe) -> str:
    return " / ".join(sorted(recipe.pages)) or "no page"


def resolve(
    citing: uuid.UUID, option: Option, book: list[BookRecipe], by_title: dict[str, list[BookRecipe]]
) -> Resolved:
    """Which recipe in the book an option's page reference means.

    by_title is the book's recipes keyed by casefolded title, so a book's
    thousand lines don't each scan its thousand recipes for a name.
    """
    if option.page is None:
        return Resolved(None)
    named = [r for r in by_title.get(option.name.casefold(), []) if r.id != citing]
    for recipe in named:
        if option.page in recipe.pages:
            return Resolved(recipe.id)
    if named:
        recipe = named[0]
        return Resolved(
            recipe.id,
            (
                FlagKind.REFERENCE_PAGE,
                f"{option.name} (p. {option.page}) is on p. {_pages(recipe)}",
            ),
        )
    on_page = [r for r in book if option.page in r.pages]
    others = [r for r in on_page if r.id != citing]
    if len(others) == 1 and len(on_page) == 1:
        return Resolved(others[0].id)
    if not on_page:
        return Resolved(
            None,
            (FlagKind.UNKNOWN_REFERENCE, f"{option.name}: no recipe on p. {option.page}"),
        )
    return Resolved(_closest(option.name, others))


_MINOR = {"a", "an", "and", "for", "in", "of", "on", "or", "the", "with"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.casefold())) - _MINOR


def _closest(name: str, candidates: list[BookRecipe]) -> uuid.UUID | None:
    """The one candidate whose title shares the most words with the name.

    On a page of stocks, "Chicken Stock" means the chicken one: "stock" adds
    the same to every candidate, so it can't decide between them. A tie, or
    no word shared, is no answer.
    """
    if not candidates:
        return None
    wanted = _words(name)
    scores = [len(wanted & _words(c.title)) for c in candidates]
    best = max(scores)
    if best == 0 or scores.count(best) > 1:
        return None
    return candidates[scores.index(best)].id
