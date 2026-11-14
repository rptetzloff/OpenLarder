"""What the server says of a page before the browser draws it.

Every page is the same index.html until the SPA fills it, so a link
preview, and any crawler that doesn't run scripts, saw the site's title and
nothing else, and an id that names nothing answered 200. For a recipe's
page, a source's, an ingredient's and an author's, the server now looks
the record up and writes the page's own head into index.html. The SPA is
unchanged: it mounts as before. *Ray's spec, 2026-11-11.*

The same goes for the body: a plain summary (the name, where a recipe is,
its ingredients by name; a source's recipes) inside the element the SPA
mounts in, which the SPA replaces as it replaced the empty one.

Only what anyone can see is ever written. Each page is built from the
API's own answer for someone signed out (routers.recipes.as_signed_out and
its sibling), whoever is asking: a private family collection's owner gets
the plain page too, and their browser fills it in. So the head has nothing
in it the API wouldn't give a stranger, and can't drift from it.

- A record that isn't there: 404, the plain page, noindex. The SPA shows
  its "not found" as before.
- One that's there but not for someone signed out (private, or waiting for
  review): 200, the plain page, noindex, nothing of the record.
- A source, an ingredient or an author merged into another: 301 to the
  one kept, if anyone can see it.

The front page and the three lists have a body too (*Ray's spec,
2026-11-13*): the first page of each, as the page asks for it with nothing
typed or chosen, as links. Whatever is typed or chosen in the address, the
summary is that first page; the browser draws what was asked for.
"""

import html
import json
import re
import uuid
from dataclasses import dataclass, replace
from datetime import date

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import visibility
from openlarder.models import Author, BookMerge, Ingredient, MergedRecord, Recipe, Source
from openlarder.routers import authors, ingredients, recipes, sources

SITE = "OpenLarder"
# A search result's snippet is cut at about this; the spec says under 160.
DESCRIPTION_MAX = 159
# Ingredients a description names before "and N more".
NAMED = 6
# How far a chain of merges is followed: A into B, B into C.
MERGE_HOPS = 5
# Recipes a source's summary lists before "All N recipes".
RECIPES_LISTED = 500


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
    # What the page shows, as plain HTML, until the SPA draws it.
    body: str = ""
    # What it's about, as schema.org things, addresses as paths.
    data: tuple[dict, ...] = ()


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


def _stop(after: str) -> str:
    """The full stop that ends a sentence, unless what it ends with has its
    own: "by Time Inc." isn't "by Time Inc..", nor "in Dinner?" "Dinner?."."""
    return "" if after.rstrip().endswith((".", "!", "?")) else "."


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


def line_names(shown: recipes.RecipeOut) -> list[str]:
    """A name for each ingredient line, in the lines' order: the first thing
    the line was matched to. A line offering a choice ("coconut oil or palm
    shortening") is one line and gets one name; a line matched to nothing
    gets none, and a name two lines share is given once."""
    names: dict[str, None] = {}
    for line in shown.lines:
        for option in line.options:
            if option.ingredient or option.recipe:
                names.setdefault(
                    option.ingredient.name if option.ingredient else option.recipe.title
                )
                break
    return list(names)


def recipe_description(shown: recipes.RecipeOut) -> str:
    """ "Banana Pancakes is on page 190 of Against All Grain by Danielle
    Walker. Ingredients: Egg, Almond Flour, Banana, and 6 more." As many
    ingredients as fit; without the authors, then cut, if it's too long.

    The names and "more" add up to the recipe's lines, the number its page
    gives beside "Ingredients", not to the names the lines hold: a line
    offering two things is one ingredient there, and so here."""
    where = f"{shown.title} {_where(shown)}"
    by = _people([c.name for c in shown.source.credits])
    first = f"{where} by {by}{_stop(by)}" if by else f"{where}{_stop(where)}"
    if len(first) > DESCRIPTION_MAX:
        first = f"{where}{_stop(where)}"
    if len(first) > DESCRIPTION_MAX:
        return _cut(first, DESCRIPTION_MAX)
    names = line_names(shown)
    for count in range(min(len(names), NAMED), 0, -1):
        rest = len(shown.lines) - count
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
    for first in (
        f"{shown.title}, {what} by {by}{_stop(by)}" if by else "",
        f"{shown.title}, {what}.",
    ):
        if first and len(f"{first} {indexed}") <= DESCRIPTION_MAX:
            return f"{first} {indexed}"
    return _cut(f"{shown.title}, {what}.", DESCRIPTION_MAX)


# The page's body, before the SPA draws it: plain HTML a crawler can read,
# inside the element the SPA mounts in and so replaced when it does. Only
# what the page itself shows anyone: titles, where a recipe is, and its
# ingredients by name. Every value goes through _e.


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _a(href: str, words: str, rel: str = "") -> str:
    rel = f' rel="{rel}"' if rel else ""
    return f'<a href="{_e(href)}"{rel}>{_e(words)}</a>'


def _listed(items: list[str]) -> str:
    """Pieces of HTML as a sentence lists them: "A", "A and B", "A, B and C"."""
    if len(items) > 1:
        return f"{', '.join(items[:-1])} and {items[-1]}"
    return items[0] if items else ""


def _by(credits) -> str:
    """ " by Ann Author and Pat Photographer", each a link to their page."""
    people = _listed([_a(f"/authors/{c.author_id}", c.name) for c in credits])
    return f" by {people}" if people else ""


def _summary(crumbs: list[str], *parts: str) -> str:
    """The summary in the page's own frame, so it sits where the page will.
    A list's page has no trail: it is the top of one."""
    trail = f'<nav aria-label="Breadcrumb">{" / ".join(crumbs)}</nav>' if crumbs else ""
    return f'<main><article class="wide">{trail}{"".join(parts)}</article></main>'


def _edition(*facts: object, isbn: str | None) -> str:
    """An edition by what tells it apart: "W. W. Norton, 2020, ISBN
    9780393541113". Whatever of it is recorded."""
    return ", ".join(_e(fact) for fact in (*facts, f"ISBN {isbn}" if isbn else None) if fact)


def _recipe_place(shown: recipes.RecipeOut) -> str:
    """Where a recipe is, as a paragraph: its source as a link, who made
    it, and the page, the issue, the episode or the web address."""
    source = _a(f"/sources/{shown.source.id}", shown.source.title) + _by(shown.source.credits)
    # What the source and its authors end with, where they end a sentence.
    credits = shown.source.credits
    stop = _stop(credits[-1].name if credits else shown.source.title)
    if shown.issue:
        page = f", page {_e(shown.issue.page)}" if shown.issue.page else ""
        return f"<p>In {source}, {_e(issue_name(shown.issue.label))}{page}.</p>"
    if shown.episode:
        at = f", at {_e(shown.episode.at)}" if shown.episode.at else ""
        return f"<p>From {source}, {_e(shown.episode.name)}{at}.</p>"
    if shown.web_address:
        address = _a(shown.web_address, shown.web_address, "nofollow noopener")
        return f"<p>From {source}: {address}</p>"
    paged = [p for p in shown.pages if p.page]
    if not paged:
        return f"<p>In {source}{stop}</p>"
    if len(paged) == 1:
        return f"<p>Page {_e(paged[0].page)} of {source}{stop}</p>"
    editions = "".join(
        f"<li>Page {_e(p.page)}: {_edition(p.edition_title, p.published_year, isbn=p.isbn13)}</li>"
        for p in paged
    )
    return f"<p>In {source}{stop}</p><ul>{editions}</ul>"


def _line(line: recipes.LineOut) -> str:
    """A line as the page shows it: each thing it names, as the source
    names it, linked to the ingredient or the recipe it is."""
    named = []
    for option in line.options:
        if option.recipe:
            words = _a(f"/recipes/{option.recipe.id}", option.name)
        elif option.ingredient:
            words = _a(f"/ingredients/{option.ingredient.id}", option.name)
        else:
            words = _e(option.name)
        named.append(f"{words} (p. {_e(option.page)})" if option.page else words)
    return " or ".join(named)


def recipe_summary(shown: recipes.RecipeOut) -> str:
    lines = "".join(f"<li>{line}</li>" for line in map(_line, shown.lines) if line)
    return _summary(
        [
            _a("/sources", "Sources"),
            _a(f"/sources/{shown.source.id}", shown.source.title),
            _e(shown.title),
        ],
        f"<h1>{_e(shown.title)}</h1>",
        _recipe_place(shown),
        f"<h2>Ingredients</h2><ul>{lines}</ul>" if lines else "",
    )


def _listed_recipe(r: sources.RecipeSummary) -> str:
    """A recipe in its source's list: its title as a link, and where."""
    where = [issue_name(r.issue)] if r.issue else []
    if r.episode:
        where.append(r.episode)
    page = next((p for p in r.pages if p), None)
    if page:
        where.append(f"page {page}")
    place = f", {_e(', '.join(where))}" if where else ""
    return f"<li>{_a(f'/recipes/{r.id}', r.title)}{place}</li>"


def source_summary(shown: sources.Book) -> str:
    what = KINDS.get(shown.kind, "a source")
    stop = _stop(shown.credits[-1].name if shown.credits else what)
    about = f"<p>{_e(what[0].upper() + what[1:])}{_by(shown.credits)}{stop}</p>"
    if shown.host:
        about += f"<p>{_a(f'https://{shown.host}', shown.host, 'nofollow noopener')}</p>"
    facts = [
        _edition(e.title, e.publisher, e.published_year, isbn=e.isbn13) for e in shown.editions
    ]
    editions = "".join(f"<li>{fact}</li>" for fact in facts if fact)
    listed = shown.recipes[:RECIPES_LISTED]
    recipes_list = "".join(_listed_recipe(r) for r in listed)
    more = ""
    if len(shown.recipes) > len(listed):
        words = f"All {len(shown.recipes):,} recipes"
        more = f"<p>{_a(f'/sources/{shown.id}', words)}</p>"
    return _summary(
        [_a("/sources", "Sources"), _e(shown.title)],
        f"<h1>{_e(shown.title)}</h1>",
        f"<p>{_e(shown.subtitle)}</p>" if shown.subtitle else "",
        about,
        f"<h2>Editions</h2><ul>{editions}</ul>" if editions else "",
        f"<h2>Recipes</h2><ul>{recipes_list}</ul>{more}" if recipes_list else "",
    )


def _fitted(first: str, lead: str, names: list[str]) -> str:
    """A sentence, then as many of the names as fit under the limit after
    the lead ("Also called"), with how many more; or the sentence alone."""
    for count in range(min(len(names), NAMED), 0, -1):
        rest = len(names) - count
        more = f", and {rest} more" if rest else ""
        whole = f"{first} {lead} {', '.join(names[:count])}{more}."
        if len(whole) <= DESCRIPTION_MAX:
            return whole
    return _cut(first, DESCRIPTION_MAX)


def ingredient_description(shown: ingredients.IngredientOut) -> str:
    """As "Cheddar is in 120 recipes indexed on OpenLarder, 480 counting what
    comes under it. Also called mature cheddar."
    """
    if shown.family_total == 0:
        first = f"No recipe indexed on OpenLarder uses {shown.name} yet."
    else:
        count = shown.total
        used = f"{count:,} recipe{'' if count == 1 else 's'} indexed on OpenLarder"
        under = shown.family_total - count
        if count == 0:
            first = (
                f"{shown.name} is in {shown.family_total:,} "
                f"recipe{'' if shown.family_total == 1 else 's'} indexed on OpenLarder, "
                "counting what comes under it."
            )
        elif under > 0:
            first = (
                f"{shown.name} is in {used}, {shown.family_total:,} counting what comes under it."
            )
        else:
            first = f"{shown.name} is in {used}."
    return _fitted(first, "Also called", [a.name for a in shown.aliases])


def _used(r: ingredients.UsedBy) -> str:
    """A recipe that uses an ingredient: its title and its source as
    links, and where in it."""
    where = [issue_name(r.issue)] if r.issue else []
    if r.episode:
        where.append(r.episode)
    if r.pages:
        where.append(f"page {r.pages[0]}")
    place = f", {_e(', '.join(where))}" if where else ""
    source = _a(f"/sources/{r.source_id}", r.source_title)
    return f"<li>{_a(f'/recipes/{r.id}', r.title)}, {source}{place}</li>"


def ingredient_summary(shown: ingredients.IngredientOut) -> str:
    about = ""
    if shown.parent:
        about += f"<p>Comes under {_a(f'/ingredients/{shown.parent.id}', shown.parent.name)}.</p>"
    if shown.aliases:
        about += f"<p>Also called {_e(', '.join(a.name for a in shown.aliases))}.</p>"
    if shown.children:
        under = _listed([_a(f"/ingredients/{c.id}", c.name) for c in shown.children])
        about += f"<p>Includes {under}.</p>"
    used = "".join(_used(r) for r in shown.recipes)
    more = ""
    if shown.listed_total > len(shown.recipes):
        words = f"All {shown.listed_total:,} recipes"
        more = f"<p>{_a(f'/ingredients/{shown.id}', words)}</p>"
    return _summary(
        [_a("/ingredients", "Ingredients"), _e(shown.name)],
        f"<h1>{_e(shown.name)}</h1>",
        about,
        f"<h2>Recipes using {_e(shown.name)}</h2><ul>{used}</ul>{more}" if used else "",
    )


def author_description(shown: authors.AuthorOut) -> str:
    """As "Danielle Walker is credited on 3 sources indexed on OpenLarder:
    Against All Grain, Meals Made Simple, and 1 more."
    """
    count = len(shown.sources)
    if count == 0:
        return _cut(f"No source indexed on OpenLarder credits {shown.name} yet.", DESCRIPTION_MAX)
    first = (
        f"{shown.name} is credited on {count:,} source{'' if count == 1 else 's'} "
        "indexed on OpenLarder"
    )
    titles = [s.title for s in shown.sources]
    # As many of the sources as fit, up to three; none, if a title is long.
    for named in range(min(count, 3), 0, -1):
        rest = count - named
        more = f", and {rest} more" if rest else ""
        whole = f"{first}: {', '.join(titles[:named])}{more}."
        if len(whole) <= DESCRIPTION_MAX:
            return whole
    return _cut(f"{first}.", DESCRIPTION_MAX)


def _credited(s: authors.AuthorBook) -> str:
    """A source an author is credited on: its title as a link, what it is,
    and how many recipes."""
    what = KINDS.get(s.kind, "a source")
    count = f"{s.recipes:,} recipe{'' if s.recipes == 1 else 's'}"
    return f"<li>{_a(f'/sources/{s.id}', s.title)}, {_e(what)}, {count}</li>"


def author_summary(shown: authors.AuthorOut) -> str:
    credited = "".join(_credited(s) for s in shown.sources)
    together = _listed([_a(f"/authors/{c.id}", c.name) for c in shown.coauthors])
    return _summary(
        [_a("/authors", "Authors"), _e(shown.name)],
        f"<h1>{_e(shown.name)}</h1>",
        f"<h2>Sources</h2><ul>{credited}</ul>" if credited else "",
        f"<p>Credited with {together}.</p>" if together else "",
    )


# Structured data (schema.org, as JSON-LD): what a page is about, for a
# search engine to read without guessing. Addresses are written as paths
# here and made whole in fill, which knows the site's address.

# What a source is, to schema.org. The rest are a CreativeWork.
SCHEMA_TYPES = {
    "book": "Book",
    "website": "WebSite",
    "magazine": "Periodical",
    "newspaper": "Periodical",
    "tv_show": "TVSeries",
    "podcast": "PodcastSeries",
}


def _trail(*steps: tuple[str, str]) -> dict:
    """The page's breadcrumb, as it shows: each step's name and address."""
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": n, "name": name, "item": path}
            for n, (name, path) in enumerate(steps, start=1)
        ],
    }


def _work(source_id: uuid.UUID, kind: str, title: str) -> dict:
    """A source, by what it is: a Book, a WebSite, a Periodical, a TVSeries."""
    return {
        "@type": SCHEMA_TYPES.get(kind, "CreativeWork"),
        "@id": f"/sources/{source_id}",
        "name": title,
        "url": f"/sources/{source_id}",
    }


def recipe_data(shown: recipes.RecipeOut) -> list[dict]:
    """A page about a recipe, never a Recipe: the page has no method and no
    amounts, and saying it's one would mislead a searcher and a search
    engine both. It's part of its source and about its ingredients."""
    page = {
        "@type": "WebPage",
        "@id": f"/recipes/{shown.id}",
        "name": shown.title,
        "url": f"/recipes/{shown.id}",
        "isPartOf": _work(shown.source.id, shown.source.kind, shown.source.title),
    }
    about = [{"@type": "Thing", "name": name} for name in ingredient_names(shown)]
    if about:
        page["about"] = about
    trail = _trail(
        ("Sources", "/sources"),
        (shown.source.title, f"/sources/{shown.source.id}"),
        (shown.title, f"/recipes/{shown.id}"),
    )
    return [page, trail]


def source_data(shown: sources.Book, organisations: set[uuid.UUID]) -> list[dict]:
    """A Book with who wrote it, its ISBN and its year (the newest
    edition's that has them); or what else the source is, by its kind."""
    work = _work(shown.id, shown.kind, shown.title)
    # Its authors; a photographer or an illustrator is a contributor.
    by_role: dict[str, list[dict]] = {}
    for credit in shown.credits:
        role = "author" if credit.role == "author" else "contributor"
        by_role.setdefault(role, []).append(
            {
                "@type": "Organization" if credit.author_id in organisations else "Person",
                "name": credit.name,
                "url": f"/authors/{credit.author_id}",
            }
        )
    work.update(by_role)
    if shown.kind == "book":
        isbn = next((e.isbn13 for e in shown.editions if e.isbn13), None)
        year = next((e.published_year for e in shown.editions if e.published_year), None)
        if isbn:
            work["isbn"] = isbn
        if year:
            work["datePublished"] = str(year)
    if shown.host:
        work["sameAs"] = f"https://{shown.host}"
    return [work, _trail(("Sources", "/sources"), (shown.title, f"/sources/{shown.id}"))]


def ingredient_data(shown: ingredients.IngredientOut) -> list[dict]:
    return [_trail(("Ingredients", "/ingredients"), (shown.name, f"/ingredients/{shown.id}"))]


def author_data(shown: authors.AuthorOut) -> list[dict]:
    """A person or an organisation, and the same one elsewhere: Wikidata,
    Open Library, their own site."""
    who = {
        "@type": "Person" if shown.kind == "person" else "Organization",
        "@id": f"/authors/{shown.id}",
        "name": shown.name,
        "url": f"/authors/{shown.id}",
    }
    same = [u for u in (shown.wikidata_url, shown.open_library_url, shown.website) if u]
    if same:
        who["sameAs"] = same
    return [who, _trail(("Authors", "/authors"), (shown.name, f"/authors/{shown.id}"))]


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
        body=recipe_summary(shown),
        data=tuple(recipe_data(shown)),
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


async def _went_to(
    session: AsyncSession, kind: str, gone_id: uuid.UUID, model, seen
) -> uuid.UUID | None:
    """The ingredient or author a merged one went into (migration 0070),
    following merges on, if anyone can see it: an address that says where a
    record went mustn't say that one that isn't everyone's is there."""
    at = gone_id
    for _ in range(MERGE_HOPS):
        merged = await session.scalar(
            select(MergedRecord.kept_id).where(
                MergedRecord.gone_id == at, MergedRecord.kind == kind
            )
        )
        if merged is None:
            break
        at = merged
    if at == gone_id:
        return None
    return await session.scalar(select(model.id).where(model.id == at, seen))


async def source(session: AsyncSession, source_id: uuid.UUID) -> Page:
    shown = await sources.as_signed_out(session, source_id)
    if shown is None:
        if await session.scalar(select(exists().where(Source.id == source_id))):
            return HIDDEN
        kept = await _kept(session, source_id)
        return Page(status=301, moved_to=f"/sources/{kept}") if kept else NOT_FOUND
    # Which of those it credits are organisations: a test kitchen isn't a Person.
    credited = [c.author_id for c in shown.credits]
    organisations = set(
        await session.scalars(
            select(Author.id).where(Author.id.in_(credited), Author.kind == "organisation")
        )
    )
    return Page(
        title=f"{shown.title} · {SITE}",
        description=source_description(shown),
        path=f"/sources/{shown.id}",
        og_type="book" if shown.kind == "book" else "website",
        body=source_summary(shown),
        data=tuple(source_data(shown, organisations)),
    )


async def ingredient(session: AsyncSession, ingredient_id: uuid.UUID) -> Page:
    """An ingredient only recipes that aren't everyone's use is as hidden
    as they are. One merged into another goes to the one kept."""
    shown = await ingredients.as_signed_out(session, ingredient_id)
    if shown is None:
        if await session.scalar(select(exists().where(Ingredient.id == ingredient_id))):
            return HIDDEN
        kept = await _went_to(
            session, "ingredient", ingredient_id, Ingredient, visibility.ingredients_seen_by(None)
        )
        return Page(status=301, moved_to=f"/ingredients/{kept}") if kept else NOT_FOUND
    return Page(
        title=f"{shown.name} · Ingredients · {SITE}",
        description=ingredient_description(shown),
        path=f"/ingredients/{shown.id}",
        body=ingredient_summary(shown),
        data=tuple(ingredient_data(shown)),
    )


async def author(session: AsyncSession, author_id: uuid.UUID) -> Page:
    shown = await authors.as_signed_out(session, author_id)
    if shown is None:
        if await session.scalar(select(exists().where(Author.id == author_id))):
            return HIDDEN
        kept = await _went_to(
            session, "author", author_id, Author, visibility.authors_seen_by(None)
        )
        return Page(status=301, moved_to=f"/authors/{kept}") if kept else NOT_FOUND
    return Page(
        title=f"{shown.name} · {SITE}",
        description=author_description(shown),
        path=f"/authors/{shown.id}",
        og_type="profile" if shown.kind == "person" else "website",
        body=author_summary(shown),
        data=tuple(author_data(shown)),
    )


# The lists: one page each to index, whatever was typed or chosen on it,
# so the address without its query is the one a search engine keeps.
LISTS = {
    "": Page(path="/"),
    "sources": Page(
        title=f"Sources · {SITE}",
        description=(
            "Cookbooks, websites, magazines and shows, with the recipes indexed from each:"
            " where every recipe is and what goes in it."
        ),
        path="/sources",
    ),
    "ingredients": Page(
        title=f"Ingredients · {SITE}",
        description=(
            "Every ingredient the indexed recipes use. Open one to see the recipes that use it."
        ),
        path="/ingredients",
    ),
    "authors": Page(
        title=f"Authors · {SITE}",
        description="The people and kitchens behind the indexed cookbooks, and what each made.",
        path="/authors",
    ),
}


def _n(count: int, one: str) -> str:
    """ "1 recipe", "1,234 recipes"."""
    return f"{count:,} {one}{'' if count == 1 else 's'}"


def _first_of(listed: int, total: int, what: str) -> str:
    """Said under a list that isn't all of them."""
    return f"<p>The first {listed:,} of {total:,} {what}.</p>" if total > listed else ""


def _listed_source(s: sources.BookSummary) -> str:
    """A source in a list: its title as a link, what it is and whose, and
    how many recipes."""
    by = _people(s.authors)
    whose = f"{KINDS.get(s.kind, 'a source')} by {by}" if by else KINDS.get(s.kind, "a source")
    return f"<li>{_a(f'/sources/{s.id}', s.title)}, {_e(whose)}, {_n(s.recipes, 'recipe')}</li>"


def _list_page(key: str, heading: str, items: list[str], total: int, what: str) -> Page:
    """A list's page with its first page of items, or with its head alone
    when it has none to show."""
    page = LISTS[key]
    if not items:
        return page
    body = _summary(
        [],
        f"<h1>{_e(heading)}</h1>",
        f"<p>{_e(page.description)}</p>",
        f"<ul>{''.join(items)}</ul>",
        _first_of(len(items), total, what),
    )
    return replace(page, body=body)


# Every argument is given: called as functions, the routes' defaults are
# FastAPI's markers, not values.
async def sources_list(session: AsyncSession) -> Page:
    """Sources, A to Z by title, as its page first shows them to someone
    signed out."""
    found = await sources.list_books(
        session, None, q="", offset=0, limit=sources.PAGE, sort="title", kind=None, min_recipes=0
    )
    items = [_listed_source(s) for s in found.sources]
    return _list_page("sources", "Sources", items, found.total, "sources")


async def ingredients_list(session: AsyncSession) -> Page:
    """Ingredients, the most used first, as its page first shows them."""
    found = await ingredients.list_ingredients(
        session, None, q="", offset=0, sort="uses", top=False, name=None
    )
    items = [
        f"<li>{_a(f'/ingredients/{i.id}', i.name)}, {_n(i.recipes, 'recipe')}</li>"
        for i in found.ingredients
    ]
    return _list_page("ingredients", "Ingredients", items, found.total, "ingredients")


async def authors_list(session: AsyncSession) -> Page:
    """Authors, A to Z as their names read, as its page first shows them."""
    found = await authors.list_authors(session, None, q="", offset=0, sort="name", kind=None)
    items = [
        f"<li>{_a(f'/authors/{a.id}', a.name)}, {_n(a.sources, 'source')},"
        f" {_n(a.recipes, 'recipe')}</li>"
        for a in found.authors
    ]
    return _list_page("authors", "Authors", items, found.total, "authors")


# The front page's own words (web/src/pages/HomePage.vue has the same;
# tests/test_pages.py reads both).
FRONT_HEADING = "Find the recipe on your shelf."
FRONT_LEDE = (
    "A free, open reference to where recipes live: which cookbook, magazine or website,"
    " which page, and what goes in it."
)
# The newest sources the front page names: its row's worth.
FRONT_ROW = 20
# The site, and that it can be searched: a title's words go to /search as q.
WEBSITE = {
    "@type": "WebSite",
    "@id": "/#website",
    "name": SITE,
    "url": "/",
    "potentialAction": {
        "@type": "SearchAction",
        "target": {"@type": "EntryPoint", "urlTemplate": "/search?q={search_term_string}"},
        "query-input": "required name=search_term_string",
    },
}


async def front(session: AsyncSession) -> Page:
    """The front page: what the site is, the ways in, and the newest
    sources with a recipe, as its row asks for them."""
    found = await sources.list_books(
        session, None, q="", offset=0, limit=FRONT_ROW, sort="recent", kind=None, min_recipes=1
    )
    ways = [
        _a("/search", "Search recipes"),
        _a("/sources", "Sources"),
        _a("/ingredients", "Ingredients"),
        _a("/authors", "Authors"),
    ]
    newest = "".join(_listed_source(s) for s in found.sources)
    body = _summary(
        [],
        f"<h1>{_e(FRONT_HEADING)}</h1>",
        f"<p>{_e(FRONT_LEDE)}</p>",
        f"<ul>{''.join(f'<li>{way}</li>' for way in ways)}</ul>",
        f"<h2>Recently added sources</h2><ul>{newest}</ul>" if newest else "",
    )
    return replace(LISTS[""], body=body, data=(WEBSITE,))


def without_record(path: str) -> Page | None:
    """What a page with no record says, by its path: the front page and
    the lists their own head, the search page and the personal ones what
    crawlers may do; None for any other, which is index.html as it is."""
    found = LISTS.get(path.strip("/"))
    if found:
        return found
    robots = robots_for(path)
    return Page(robots=robots) if robots else None


# Pages that are someone's own, or the admins': never in a search engine.
# Sign-in's two are here too: nothing on them is about the catalog.
PERSONAL = (
    "saved",
    "shelf",
    "larder",
    "groups",
    "account",
    "admin",
    "requests",
    "welcome",
    "sign-in-failed",
)


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


# The keys whose values are addresses, written as paths until fill.
ADDRESSES = {"@id", "url", "item", "urlTemplate"}


def _whole(value, site: str):
    """Structured data with its paths made whole addresses."""
    if isinstance(value, dict):
        return {
            key: f"{site}{v}"
            if key in ADDRESSES and isinstance(v, str) and v.startswith("/")
            else _whole(v, site)
            for key, v in value.items()
        }
    if isinstance(value, list):
        return [_whole(v, site) for v in value]
    return value


def json_ld(data: tuple[dict, ...] | list[dict], site_url: str) -> str:
    """One JSON-LD block. "<" is written as its escape, so nothing in a
    title can end the script."""
    graph = {"@context": "https://schema.org", "@graph": _whole(list(data), site_url.rstrip("/"))}
    text = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script type="application/ld+json">{text}</script>'


# Where the SPA mounts: empty in index.html, and whatever is put there is
# replaced when it does.
MOUNT = re.compile(r'(<div id="app">)\s*(</div>)')


def fill(shell: str, page: Page, site_url: str) -> str:
    """index.html with the page's own head, and its summary where the SPA
    mounts. Every value is escaped."""
    if page.body:
        shell = MOUNT.sub(lambda m: m.group(1) + page.body + m.group(2), shell, count=1)
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
    if page.data:
        more.append(json_ld(page.data, site_url))
    return shell.replace("</head>", f"{''.join(more)}</head>", 1) if more else shell
