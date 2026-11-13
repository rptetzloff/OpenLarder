"""Which of the recipes a title search finds come first.

*Ray's round 2 spec, 2026-11-13.* A title search finds every recipe with
each word somewhere in its title (routers/search.py), so "cake" finds
"Cheesecake" and "Pancakes" too, and it listed them by book: "Banana Mouse
Pancakes" came first of 896. They're all still found. Now, in order:

1. Every word is a whole word of the title, in Postgres's English reading
   of both, so a plural counts: "Carrot Cake" and "Crab Cakes" for "cake".
2. Every word begins a word of the title: "Cakewalk Cookies".
3. The rest, with the words inside others: "Pancakes", "Cheesecake".

Within each: a title that is exactly what was typed, then the rated
recipes, best first (routers/ratings.py), then the shorter title; the
caller ends with the title A to Z.

With ingredients too, what you have still ranks first (search.py) and this
only orders recipes level on that.

What the English reading costs: it drops words like "the" and "and", so a
search for "the" alone has nothing in the first group, and "The Best
Brownies" ranks with "Thermidor" in the second.

No index is added for it, where the spec asked for two. The trigram index
that finds the titles has been there since migration 0001. A GIN index on
to_tsvector('english', title) can only serve a WHERE; this is an ORDER BY
over rows already found, and the planner left such an index unused when
it was tried. Measured on a table of the live catalog's size (18,859
titles, 2026-11-13): "cake" (896 found) 4.7 ms ranked against 2.2 ms by
book; "chicken" (981) 5.6 ms; a single letter that's in nearly every title,
the worst there is, 136 ms against 15 ms. If that ever matters, what would
help is the reading stored in a column, not the index.
"""

import re
from collections.abc import Sequence

from sqlalchemy import ColumnElement, and_, case, func, literal_column

from openlarder.models import Recipe

# A constant in the SQL, as to_tsvector's first argument must be for
# Postgres to treat the reading as fixed for a title.
ENGLISH = literal_column("'english'")


def order(
    words: Sequence[str], typed: str, rated_first: Sequence[ColumnElement] = ()
) -> list[ColumnElement]:
    """ORDER BY terms for a search by these title words: `typed` is the
    search as it was typed, tidied; `rated_first` puts rated recipes in
    order. Nothing for a search with no words."""
    if not words:
        return []
    whole = func.to_tsvector(ENGLISH, Recipe.title).op("@@")(
        func.plainto_tsquery(ENGLISH, " ".join(words))
    )
    # \m is the start of a word. The word itself is escaped: it's what
    # someone typed, and "c++" or "(" isn't a pattern.
    begins = and_(*(Recipe.title.op("~*")(r"\m" + re.escape(word)) for word in words))
    return [
        case((whole, 0), (begins, 1), else_=2),
        case((func.lower(Recipe.title) == func.lower(typed), 0), else_=1),
        *rated_first,
        func.char_length(Recipe.title),
    ]
