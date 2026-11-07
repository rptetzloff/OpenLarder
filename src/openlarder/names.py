"""Display names: what a person is shown as beside their contributions.

A display name is chosen in OpenLarder, not taken from the sign-in
provider, because it is public: Google's or GitHub's name for someone is
often their full legal name. It is unique, compared case-insensitively, so
that an edit history can tell two contributors apart. *Decided by Ray,
2026-11-07.*

Normalising with NFKC folds look-alike forms of the same character
(full-width letters, ligatures) before comparing. It does not catch
look-alikes from different scripts, such as Cyrillic "а" for Latin "a";
that is a known limit, and moderation's to handle.
"""

import re
import unicodedata

MIN_LENGTH = 2
MAX_LENGTH = 32

# Names that would read as speaking for the site. *Chosen by Claude,
# 2026-11-07*; a new one is a one-line change.
RESERVED = frozenset(
    {
        "admin",
        "administrator",
        "anonymous",
        "deleted",
        "mod",
        "moderator",
        "official",
        "openlarder",
        "root",
        "staff",
        "support",
        "system",
    }
)

# Letters and digits in any script, joined by single spaces or . _ - '
_SHAPE = re.compile(r"[^\W_](?:[ ._'\-]?[^\W_])*")


class InvalidName(ValueError):
    """The reason is written to be shown to the person choosing the name."""


def normalise(raw: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", raw).split())


def validate(raw: str) -> str:
    """Return the name as it will be stored, or raise InvalidName."""
    name = normalise(raw)
    if len(name) < MIN_LENGTH:
        raise InvalidName(f"Use at least {MIN_LENGTH} characters.")
    if len(name) > MAX_LENGTH:
        raise InvalidName(f"Use at most {MAX_LENGTH} characters.")
    if not _SHAPE.fullmatch(name):
        raise InvalidName(
            "Use letters and numbers, with single spaces, dots, dashes, underscores or"
            " apostrophes between them."
        )
    if name.casefold() in RESERVED:
        raise InvalidName("That name is reserved.")
    return name


def suggestion(raw: str | None) -> str | None:
    """The sign-in provider's name, if it would pass as a display name."""
    if not raw:
        return None
    try:
        return validate(raw)
    except InvalidName:
        return None
