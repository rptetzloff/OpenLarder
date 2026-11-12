"""What the server says of a page before the browser draws it.

Every page is the same index.html until the SPA fills it, so a link
preview, and any crawler that doesn't run scripts, saw the site's title and
nothing else, and an id that names nothing answered 200. For a recipe's
page and a source's, the server now looks the record up and writes the
page's own head into index.html. The SPA is unchanged: it mounts as before.
*Ray's spec, 2026-11-11.*

Only what anyone can see is ever written. Each page is built from the
API's own answer for someone signed out (routers.recipes.as_signed_out and
its sibling), whoever is asking: a private family collection's owner gets
the plain page too, and their browser fills it in. So the head has nothing
in it the API wouldn't give a stranger, and can't drift from it.

- A record that isn't there: 404, the plain page, noindex. The SPA shows
  its "not found" as before.
- One that's there but not for someone signed out (private, or waiting for
  review): 200, the plain page, noindex, nothing of the record.
- A source merged into another: 301 to the one kept, if anyone can see it.
"""

import html
import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import visibility
from openlarder.models import BookMerge, Recipe, Source
from openlarder.routers import recipes, sources

SITE = "OpenLarder"
# A search result's snippet is cut at about this; the spec says under 160.
DESCRIPTION_MAX = 159
# Ingredients a description names before "and N more".
NAMED = 6
# How far a chain of merges is followed: A into B, B into C.
MERGE_HOPS = 5


@dataclass(frozen=True)
class Page:
    status: int = 200
    # None: index.html's own, the site's.
    title: str | None = None
    description: str | None = None
    # The page's own address, as a path: its canonical link and og:url.
    path: str | None = None
    og_type: str = "website"
    # "noindex", or "noindex, follow" for the search page.
    robots: str | None = None
    # Where it went: a path to answer 301 with.
    moved_to: str | None = None


NOT_FOUND = Page(status=404, robots="noindex")
# There, but not for someone signed out: nothing of it is said.
HIDDEN = Page(robots="noindex")

# What a source is, in a sentence.
KINDS = {
    "book": "a book",
    "website": "a website",
    "magazine": "a magazine",
    "newspaper": "a newspaper",
    "tv_show": "a TV show",
    "podcast": "a podcast",
    "video_channel": "a video channel",
    "social": "a social media account",
    "packaging": "a product",
    "family": "a family collection",
}


def _people(names: list[str]) -> str:
    """Names as a sentence has them: "A", "A and B", "A, B and C"; past
    three, "A and others"."""
    if len(names) > 3:
        return f"{names[0]} and others"
    if len(names) > 1:
        return f"{', '.join(names[:-1])} and {names[-1]}"
    return names[0] if names else ""


def issue_name(label: str) -> str:
    """An issue as people say it: one named by its date in words, any
    other as named (the SPA's issueName)."""
    try:
        day = date.fromisoformat(label)
    except ValueError:
        return label
    return f"{day:%B} {day.day}, {day.year}"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,;:") + "…"


def _where(shown: recipes.RecipeOut) -> str:
    """Where a recipe is, to follow its title: "is on page 190 of Against
    All Grain"."""
    source = shown.source.title
    if shown.issue:
        page = f", page {shown.issue.page}" if shown.issue.page else ""
        return f"is in {source}, {issue_name(shown.issue.label)}{page}"
    if shown.episode:
        return f"is from {source}, {shown.episode.name}"
    if shown.web_address or shown.source.kind == "website":
        return f"is from {source}"
    # The newest edition it has a page in.
    page = next((p.page for p in shown.pages if p.page), None)
    return f"is on page {page} of {source}" if page else f"is in {source}"


def ingredient_names(shown: recipes.RecipeOut) -> list[str]:
    """The ingredients a recipe's lines were matched to, and the recipes
    they cite, each once, in the lines' order."""
    names: dict[str, None] = {}
    for line in shown.lines:
        for option in line.options:
            if option.ingredient:
                names.setdefault(option.ingredient.name)
            elif option.recipe:
                names.setdefault(option.recipe.title)
    return list(names)


def recipe_description(shown: recipes.RecipeOut) -> str:
    """ "Banana Pancakes is on page 190 of Against All Grain by Danielle
    Walker. Ingredients: Egg, Almond Flour, Banana, and 6 more." As many
    ingredients as fit; without the authors, then cut, if it's too long."""
    where = f"{shown.title} {_where(shown)}"
    by = _people([c.name for c in shown.source.credits])
    first = f"{where} by {by}." if by else f"{where}."
    if len(first) > DESCRIPTION_MAX:
        first = f"{where}."
    if len(first) > DESCRIPTION_MAX:
        return _cut(first, DESCRIPTION_MAX)
    names = ingredient_names(shown)
    for count in range(min(len(names), NAMED), 0, -1):
        rest = len(names) - count
        more = f", and {rest} more" if rest else ""
        whole = f"{first} Ingredients: {', '.join(names[:count])}{more}."
        if len(whole) <= DESCRIPTION_MAX:
            return whole
    return first


def source_description(shown: sources.Book) -> str:
    """ "Against All Grain, a book by Danielle Walker. 152 recipes indexed,
    each with where to find it and its ingredients.\""""
    by = _people([c.name for c in shown.credits])
    what = KINDS.get(shown.kind, "a source")
    count = len(shown.recipes)
    if count == 0:
        indexed = "No recipes indexed yet."
    elif count == 1:
        indexed = "1 recipe indexed, with where to find it and its ingredients."
    else:
        indexed = f"{count:,} recipes indexed, each with where to find it and its ingredients."
    for first in (f"{shown.title}, {what} by {by}." if by else "", f"{shown.title}, {what}."):
        if first and len(f"{first} {indexed}") <= DESCRIPTION_MAX:
            return f"{first} {indexed}"
    return _cut(f"{shown.title}, {what}.", DESCRIPTION_MAX)


async def recipe(session: AsyncSession, recipe_id: uuid.UUID) -> Page:
    shown = await recipes.as_signed_out(session, recipe_id)
    if shown is None:
        there = await session.scalar(select(exists().where(Recipe.id == recipe_id)))
        return HIDDEN if there else NOT_FOUND
    return Page(
        title=f"{shown.title} · {shown.source.title} · {SITE}",
        description=recipe_description(shown),
        path=f"/recipes/{shown.id}",
        og_type="article",
    )


async def _kept(session: AsyncSession, gone_id: uuid.UUID) -> uuid.UUID | None:
    """The source a merged one went into, following merges on, if anyone
    can see it. A merge that was undone put its source back."""
    at = gone_id
    for _ in range(MERGE_HOPS):
        merged = await session.scalar(
            select(BookMerge.kept_id)
            .where(BookMerge.gone_id == at, BookMerge.undone_at.is_(None))
            .order_by(BookMerge.merged_at.desc())
            .limit(1)
        )
        if merged is None:
            break
        at = merged
    if at == gone_id:
        return None
    return await session.scalar(
        select(Source.id).where(Source.id == at, visibility.sources_seen_by(None))
    )


async def source(session: AsyncSession, source_id: uuid.UUID) -> Page:
    shown = await sources.as_signed_out(session, source_id)
    if shown is None:
        if await session.scalar(select(exists().where(Source.id == source_id))):
            return HIDDEN
        kept = await _kept(session, source_id)
        return Page(status=301, moved_to=f"/sources/{kept}") if kept else NOT_FOUND
    return Page(
        title=f"{shown.title} · {SITE}",
        description=source_description(shown),
        path=f"/sources/{shown.id}",
        og_type="book" if shown.kind == "book" else "website",
    )


# Pages that are someone's own, or the admins': never in a search engine.
PERSONAL = ("saved", "shelf", "larder", "groups", "account", "admin", "requests")


def robots_for(path: str) -> str | None:
    """What a page with no record says to crawlers, by its path: the search
    page's results aren't indexed but its links are followed; personal and
    admin pages aren't indexed."""
    first = path.strip("/").split("/")[0]
    if first == "search":
        return "noindex, follow"
    return "noindex" if first in PERSONAL else None


def _meta(attribute: str, name: str, content: str) -> str:
    return f'<meta {attribute}="{name}" content="{html.escape(content, quote=True)}" />'


def _put(shell: str, pattern: str, tag: str) -> str:
    """The tag in place of index.html's own, or at the end of the head if
    index.html has none: never both."""
    found = re.search(pattern, shell, flags=re.IGNORECASE | re.DOTALL)
    if found:
        return shell[: found.start()] + tag + shell[found.end() :]
    return shell.replace("</head>", f"{tag}</head>", 1)


def fill(shell: str, page: Page, site_url: str) -> str:
    """index.html with the page's own head. Every value is escaped."""
    if page.title is not None:
        title = f"<title>{html.escape(page.title)}</title>"
        shell = _put(shell, r"<title>.*?</title>", title)
        shell = _put(
            shell,
            r'<meta\s+property="og:title"[^>]*>',
            _meta("property", "og:title", page.title),
        )
    if page.description is not None:
        shell = _put(
            shell,
            r'<meta\s+name="description"[^>]*>',
            _meta("name", "description", page.description),
        )
        shell = _put(
            shell,
            r'<meta\s+property="og:description"[^>]*>',
            _meta("property", "og:description", page.description),
        )
    more = []
    if page.path is not None:
        address = html.escape(f"{site_url.rstrip('/')}{page.path}", quote=True)
        more.append(f'<link rel="canonical" href="{address}" />')
        more.append(f'<meta property="og:url" content="{address}" />')
        more.append(_meta("property", "og:type", page.og_type))
    if page.robots:
        more.append(_meta("name", "robots", page.robots))
    return shell.replace("</head>", f"{''.join(more)}</head>", 1) if more else shell
