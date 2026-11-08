"""How an author's name is compared: the key two spellings of one name share.

Used for matching a typed or imported name to an author already here, and
an Open Library author to a book's credit. Kept apart from the models'
module so the model can keep the key with the name.
"""

import re
import unicodedata


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
