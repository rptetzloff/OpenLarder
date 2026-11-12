"""Authors' names: how one is compared, and how a credit's is shown.

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
COMPANY = {"inc", "ltd", "llc", "co"}
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
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", name.casefold()).split())


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
    dates go, and "Last, First" turns round. A name that is already as
    printed is left alone, comma or not: "Sarah Ballantyne, PhD", "Sunset
    Books, Inc.", and an organisation's. Ray's cleanup pass, section 6.
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
        return ", ".join(parts)
    if len(parts) == 2 and not _after_the_name(parts[1]):
        return f"{_no_full_stop(parts[1])} {parts[0]}"
    if len(parts) == 3 and _bare(parts[2]) in SUFFIXES and not _after_the_name(parts[1]):
        return f"{parts[1]} {parts[0]} {parts[2]}"
    return ", ".join(parts)


def _no_full_stop(first: str) -> str:
    """A catalogue ends a name with a full stop ("Reinhart, Peter."), which
    isn't the name's; an initial's is ("Smith, John A.")."""
    last = first.split()[-1]
    if last.endswith(".") and last[:-1].isalpha() and len(last) > 3:
        return first[:-1]
    return first


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
