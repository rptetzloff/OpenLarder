"""The entry rules, checked on one ingredient line (issue #26).

A line names an ingredient as the book does, and nothing else: no amount,
no prep, nothing optional, and not salt, pepper, sugar or water unless it's
a special kind or the point of the recipe (SCOPING, "Entry rules"). A line
that starts with a number and a unit is refused outright (recipes.AMOUNT);
this catches what gets past that, and says what the bare ingredient is.

Nothing here changes a line. The form shows the problems and offers the
suggestion with a click; an import flags them for a person to confirm or
dismiss (*Ray, 2026-11-08*), since the stop list's exceptions can't be
decided from the line alone.

Measured on the household index, which follows the rules: of 140,638
options, only the stop list fires (609 uses: Sugar 347, Water 178, Salt
58), as it should. The rules are narrow on purpose, because a book's names
look like amounts and prep: "Half-and-Half", "Five-Spice Powder", "160
Bloom Gelatin", "Diced Tomato (Can)", "Shredded Coconut", "Large Shrimp"
and "Clove Essential Oil" are all ingredients. So prep is caught after a
comma or behind an adverb ("onion, diced"; "finely chopped onion"), never
as a bare first word, and a size only after a count ("3 large eggs").
Brands aren't detected: telling one from an ingredient needs a list.
"""

import re
from dataclasses import dataclass, field

from openlarder import lines
from openlarder.ingredients import match_key

_NUMBER_WORDS = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
_AMOUNT_WORDS = rf"an?|{_NUMBER_WORDS}|half|a few|a couple(?: of)?|several|some"
# Units that are never an ingredient's first word. Cloves, heads, sticks
# and the like are ("Clove Essential Oil"), so they count only with "of".
_UNITS = (
    r"cups?|tbsps?|tbs|tablespoons?|tsps?|teaspoons?|ounces?|oz|grams?|kg|lbs?|pounds?"
    r"|ml|litres?|liters?|pinch(?:es)?|dash(?:es)?|handfuls?|splash(?:es)?|drizzle"
)
_PIECES = (
    r"cloves?|heads?|sticks?|slices?|pieces?|stalks?|sprigs?|bunch(?:es)?|cans?|tins?"
    r"|jars?|packages?|knobs?"
)
_SIZES = r"large|small|medium|jumbo|extra[- ]large"
_ADVERBS = r"very|finely|roughly|coarsely|thinly|freshly|lightly"
_PREP = (
    r"chopped|diced|minced|sliced|softened|melted|peeled|grated|beaten|halved|quartered"
    r"|cubed|shredded|trimmed|rinsed|drained|seeded|deseeded|pitted|cored|crushed|torn"
    r"|mashed|sifted|toasted|cooled|warmed|divided"
)
# "Ground" is a form ("Ground Cloves"), so it's prep only behind an adverb.
_NOTES = (
    r"(?:at )?room temperature|to taste|for (?:serving|garnish|garnishing|dusting|frying"
    r"|greasing|brushing)|plus (?:more|extra)\b.*|or (?:more|extra)\b.*|cut into\b.*"
)

_AMOUNT = re.compile(
    rf"^(?:(?:{_AMOUNT_WORDS})\s+(?:(?:{_UNITS}|{_PIECES})\s+of\s+|(?:{_UNITS})\s+|of\s+)"
    rf"|half\s+an?\s+|(?:{_UNITS})\s+(?:of\s+)?"
    rf"|(?:[1-9]\d*|an?|{_NUMBER_WORDS})\s+(?:(?:{_SIZES})\s+)?"
    rf"(?:(?:{_UNITS})\s+(?:of\s+)?|(?:{_PIECES})\s+of\s+)?"
    rf"(?!spice\b|bloom\b|proof\b|minute\b))",
    re.IGNORECASE,
)
# The amount words can begin a name ("Half-and-Half"), so each needs a space
# after it; "Five Spice" is a spice and "160 Bloom Gelatin" a gelatin. A
# piece without a count is a name too ("Head of Small Fish").
_TAIL = re.compile(
    rf"\s*,\s*(?:(?:{_ADVERBS})\s+)?(?:{_PREP}|{_NOTES})\b.*$|\s+(?:{_NOTES})$",
    re.IGNORECASE,
)
_ADVERB_PREP = re.compile(rf"\b(?:{_ADVERBS})\s+(?:{_PREP}|ground)\s+", re.IGNORECASE)
_OPTIONAL = re.compile(r"\b(?:optional|if desired|if you like|if using)\b", re.IGNORECASE)

# Plain kinds only: sea salt, white pepper and brown sugar aren't on it.
STOP_LIST = frozenset(
    match_key(n)
    for n in (
        "salt",
        "table salt",
        "kosher salt",
        "fine salt",
        "pepper",
        "black pepper",
        "ground black pepper",
        "ground pepper",
        "salt and pepper",
        "sugar",
        "white sugar",
        "granulated sugar",
        "white granulated sugar",
        "water",
        "cold water",
        "warm water",
        "hot water",
        "boiling water",
        "lukewarm water",
        "ice water",
    )
)

AMOUNT = "Leave out the amount; the book has it."
PREP = "Leave out prep and serving notes."
OPTIONAL = "Optional items are left out."
LEFT_OUT = (
    "Salt, pepper, sugar and water are left out, unless it's a special kind"
    " or the point of the recipe."
)


@dataclass
class Review:
    problems: list[str] = field(default_factory=list)
    # The line as the rules would have it, when that's a change.
    suggestion: str | None = None
    # The rules would leave the whole line out.
    remove: bool = False


def _bare(name: str, problems: list[str]) -> str:
    stripped = _AMOUNT.sub("", name, count=1)
    # An amount always leaves something: each form ends in a space.
    if stripped != name:
        problems.append(AMOUNT)
        name = stripped
    trimmed = _ADVERB_PREP.sub("", _TAIL.sub("", name))
    if trimmed != name and trimmed.strip():
        problems.append(PREP)
        name = trimmed
    return " ".join(name.split())


def _join(names: list[str]) -> str:
    if len(names) < 3:
        return " or ".join(names)
    return ", ".join(names[:-1]) + ", or " + names[-1]


def review(line: str) -> Review:
    """What the entry rules say about one line."""
    line = " ".join(line.split())
    if not line:
        return Review()
    if _OPTIONAL.search(line):
        return Review(problems=[OPTIONAL], remove=True)
    options = lines.options(line)
    problems: list[str] = []
    names = []
    for option in options:
        if option.page is not None:
            # A reference to another recipe: kept exactly as written.
            names.append(f"{option.name} (p. {option.page})")
        else:
            names.append(_bare(option.name, problems))
    # Checked on the bare name, so "Salt, to taste" is left out too.
    if len(options) == 1 and options[0].page is None and match_key(names[0]) in STOP_LIST:
        return Review(problems=[LEFT_OUT], remove=True)
    if not problems:
        return Review()
    return Review(problems=list(dict.fromkeys(problems)), suggestion=_join(names))


TWICE = "Already listed above; each ingredient goes in once."


def review_all(entered: list[str]) -> list[Review]:
    """Each line's review, and a line repeating an earlier one marked to go."""
    reviews = []
    seen: set[str] = set()
    for line in entered:
        found = review(line)
        key = match_key(found.suggestion or line)
        if key and not found.remove and key in seen:
            found = Review(problems=[TWICE], remove=True)
        seen.add(key)
        reviews.append(found)
    return reviews
