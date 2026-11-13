"""Authors' names: how one is compared, how a credit's is shown, and how
one is filed in a list by last name.

Compared: the key two spellings of one name share, for matching a typed or
imported name to an author already here, and an Open Library author to a
book's credit. Shown: a credit kept in a catalogue's form ("Walker,
Danielle (Chef)") reads as a book would print it ("Danielle Walker"),
without what is stored changing. Kept apart from the models' module so the
model can keep the key with the name.
"""

import re
import unicodedata

# A bracketed note that says the name is an organisation's: "(Firm)".
ORGANISATION = {
    "firm",
    "organization",
    "organisation",
    "company",
    "corporation",
    "restaurant",
    "society",
    "association",
}
# A last part that is a suffix, not a first name: "King, Martin, Jr.".
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
# A last part that is a company's, not a first name: "Sunset Books, Inc.".
COMPANY = {"inc", "ltd", "llc", "co", "corp", "bros"}
# Letters after a name, which a book prints there: "Sarah Ballantyne, PhD".
CREDENTIALS = {
    "phd",
    "md",
    "do",
    "nd",
    "dc",
    "dds",
    "dvm",
    "rd",
    "rdn",
    "rn",
    "ms",
    "ma",
    "mph",
    "mba",
    "msc",
    "bsc",
    "cnc",
    "cns",
    "ntp",
    "lac",
    "cpt",
    "esq",
    "obe",
    "mbe",
    "cbe",
}
# A catalogue's dates after a name: "1912-2004", "1950-", "b. 1950".
_DATES = re.compile(r"(b\. ?)?\d{4}(-(\d{4})?)?\.?")
_TRAILING_NOTES = re.compile(r"(\s*\([^)]*\))+$")


def name_key(name: str) -> str:
    """A name reduced for matching: "Moore, Russell (Chef)" -> "russell moore".

    Bracketed notes go, "Last, First" turns round, and accents, case and
    punctuation are ignored. Authors keep theirs (migration 0022), so a
    typed name finds the author it means.
    """
    name = re.sub(r"\([^)]*\)", " ", name)
    if name.count(",") == 1:
        last, first = name.split(",")
        name = f"{first} {last}"
    return _folded(name)


def _folded(text: str) -> str:
    """Without accents, case or punctuation, and single-spaced."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


def _bare(part: str) -> str:
    """A part of a name as compared with the sets above: "Ph.D." -> "phd"."""
    return part.casefold().replace(".", "").strip()


def _after_the_name(part: str) -> bool:
    """Whether a part is letters after a name, not a first name: "PhD",
    "MS, RD", "Jr.", "Inc."."""
    words = [_bare(w) for w in re.split(r"[\s,]+", part) if w]
    return bool(words) and all(w in CREDENTIALS | SUFFIXES | COMPANY for w in words)


def display_name(name: str) -> str:
    """A name as a book would print it: "Walker, Danielle (Chef)" ->
    "Danielle Walker".

    A bracketed note at the end goes (a role, dates, "Firm"), a catalogue's
    dates go, "Last, First" turns round, and the full stop a catalogue ends
    a name with goes ("Culinary Institute of America."). A name that is
    already as printed is left alone, comma or not: "Sarah Ballantyne,
    PhD", "Sunset Books, Inc.", and an organisation's. Ray's cleanup pass,
    section 6.
    """
    spaced = " ".join(name.split())
    notes = [n.strip().casefold().rstrip(".") for n in re.findall(r"\(([^)]*)\)", spaced)]
    shown = _TRAILING_NOTES.sub("", spaced).strip()
    if not shown:
        return spaced or name
    parts = [p.strip() for p in shown.split(",")]
    while len(parts) > 1 and _DATES.fullmatch(parts[-1]):
        parts.pop()
    if not all(parts):
        return shown
    if any(n in ORGANISATION for n in notes) or len(parts) == 1:
        return _no_full_stop(", ".join(parts))
    if len(parts) == 2 and not _after_the_name(parts[1]):
        return f"{_no_full_stop(parts[1])} {parts[0]}"
    if len(parts) == 3 and _bare(parts[2]) in SUFFIXES and not _after_the_name(parts[1]):
        return f"{parts[1]} {parts[0]} {parts[2]}"
    return ", ".join(parts)


def _no_full_stop(first: str) -> str:
    """A catalogue ends a name with a full stop ("Reinhart, Peter."), which
    isn't the name's. An initial's is ("Smith, John A."), and so is an
    abbreviation's: "Jr.", "Inc.", "Ph.D."."""
    last = first.split()[-1]
    if (
        last.endswith(".")
        and last[:-1].isalpha()
        and len(last) > 3
        and _bare(last) not in SUFFIXES | COMPANY | CREDENTIALS
    ):
        return first[:-1]
    return first


# Letters after a name that CREDENTIALS doesn't list: a full stop after one
# of those is kept as the abbreviation's own, and "PharmD." has been seen
# with a catalogue's (display_name).
_ALSO_AFTER_A_NAME = {"pharmd"}
# Words that begin a last name when written with a capital: "Van Damme".
_PARTICLES = {"van", "von", "de", "del", "della", "der", "den", "di", "da", "du", "la", "le"}


def surname_key(name: str, organisation: bool = False) -> str:
    """What an author is filed by in a list by last name: "Yotam Ottolenghi"
    -> "ottolenghi yotam". *Ray, 2026-11-12.*

    A person by their last name, then the rest. Letters after the name
    aren't the last name ("Sarah Ballantyne, PhD", "Martin Luther King
    Jr."), nor is what follows a comma. A particle written with a capital
    begins the last name ("Eddy Van Damme" is under V); in lower case it
    goes with the first names ("Oscar de la Renta" is under R), as a
    library files it. A single name is filed as it is. An organisation is
    filed by its name, less a leading "The": who is which is the author's
    kind, so one marked as a person is filed by its last word until that's
    put right.

    It can't tell a last name of two words from a middle name: "Mónica
    Fernández Perea" is filed under Perea, not Fernández.
    """
    shown = display_name(name)
    if organisation:
        return _folded(re.sub(r"^the\s+", "", shown, flags=re.IGNORECASE))
    words = shown.split(",")[0].split()
    after = CREDENTIALS | SUFFIXES | _ALSO_AFTER_A_NAME
    while len(words) > 1 and _bare(words[-1]) in after:
        words.pop()
    if not words:
        return _folded(shown)
    start = len(words) - 1
    while start > 1 and words[start - 1][0].isupper() and _bare(words[start - 1]) in _PARTICLES:
        start -= 1
    return _folded(" ".join([*words[start:], *words[:start]]))


def shown_name(credited_as: str, author_name: str) -> str:
    """The name to show for a credit.

    As the book prints it, which is what a credit stores, unless that is a
    catalogue's form: then the author's own name when it is the same name
    and isn't in that form too (so an admin's fix to the author is what
    shows), and otherwise the form turned round.
    """
    plain = display_name(credited_as)
    if plain == credited_as:
        return credited_as
    same = name_key(author_name) == name_key(credited_as)
    return author_name if same and display_name(author_name) == author_name else plain
