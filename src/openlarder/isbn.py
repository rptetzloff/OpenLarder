"""ISBNs: what people type, turned into the ISBN-13 the catalog stores.

The database checks only the shape (97[89] and ten more digits); the check
digit is checked here, so a typo is refused before it is looked up rather
than after. ISBN-10s are converted, since every one has an ISBN-13 twin
with the 978 prefix.
"""

import re


class InvalidIsbn(ValueError):
    """The reason is written to be shown to the person who typed it."""


def _isbn13_check(first12: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)


def _isbn10_valid(isbn10: str) -> bool:
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(isbn10))
    return total % 11 == 0


def normalise(raw: str) -> str:
    """Return the ISBN-13 for what was typed, or raise InvalidIsbn.

    Spaces and hyphens are ignored, as books print them either way.
    """
    digits = re.sub(r"[\s-]", "", raw).upper()
    if re.fullmatch(r"\d{9}[\dX]", digits):
        if not _isbn10_valid(digits):
            raise InvalidIsbn("That ISBN-10's check digit doesn't match. Check for a typo.")
        first12 = "978" + digits[:9]
        return first12 + _isbn13_check(first12)
    if re.fullmatch(r"97[89]\d{10}", digits):
        if _isbn13_check(digits[:12]) != digits[12]:
            raise InvalidIsbn("That ISBN's check digit doesn't match. Check for a typo.")
        return digits
    raise InvalidIsbn("An ISBN is 10 or 13 digits, usually on the back cover or copyright page.")
