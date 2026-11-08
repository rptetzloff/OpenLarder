"""Recipe entries: a title, a page per edition, and the ingredients it uses.

OpenLarder is a reference to what is in cookbooks, not a recipe site. An
entry says where a recipe is and what goes in it, so it can be found by
ingredient; the amounts, the method and the headnote stay in the book.
*Ray, 2026-11-07.* So the only free text is the ingredients, each named as
the book names it ("caster sugar") with no amount; matching them to
canonical ingredients is a later step and changes nothing typed.

A line that starts with an amount ("200g rhubarb", "2 cups milk", "½ cup
milk") is refused: a number with a unit after it, or a fraction. A number
alone is not an amount ("00 flour", "2% milk"). Counts ("3 eggs") and
amounts in words ("a pinch of salt") get past it; the form's wording asks
for the ingredient alone, and detector.py points them out in the form and
flags them on import.

A recipe appears in the editions listed for it. A page left blank means it
is in that edition but the page isn't recorded yet; an edition not listed
means the recipe isn't in it. *That settles the open question in SCOPING
of an edition whose page is unknown; chosen by Claude, 2026-11-07, as the
model's docstring already described.*
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import web
from openlarder.models import (
    Edition,
    Episode,
    Issue,
    Recipe,
    RecipeIngredient,
    RecipeLocation,
    Source,
    WebPage,
)

MAX_TITLE = 200
MAX_PAGE = 20
# An ingredient's name, not a line of method: "grapeseed oil or olive oil".
# 150, not 100: the household index's longest lines, long "A or B" choices,
# run to 116 characters.
MAX_LINE = 150
MAX_LINES = 150
# An amount at the start: a vulgar fraction ("½ cup"), or a number followed by
# a unit ("200g", "2 cups", "1-2 tsp", "1/2 lb"). A number alone is not one:
# "00 flour", "2% milk", "160 bloom gelatin", "7-minute frosting" and
# "80-proof vodka" are ingredients, which the household index showed a
# digit-only rule refusing. Counts without a unit ("3 eggs") get past this;
# detector.py points those out. "c" for cup is left out, since it would
# catch temperatures ("63.5C eggs").
_UNITS = (
    "g|gr|grams?|kg|kilos?|kilograms?|mg|ml|millilitres?|milliliters?|cl|dl|l|litres?|liters?"
    "|oz|ounces?|lbs?|pounds?|cups?|tbsps?|tbs|tablespoons?|tsps?|teaspoons?|pints?|pt"
    "|quarts?|qts?|gallons?|pinch(?:es)?|dash(?:es)?|handfuls?|sticks?|cans?|tins?|jars?"
    "|packages?|pkgs?|packets?|sachets?|slices?|sprigs?|bunch(?:es)?|cloves?|heads?|knobs?"
)
AMOUNT = re.compile(
    rf"^(?:[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]|\d+(?:[.,/]\d+)?(?:\s*(?:-|–|to)\s*\d+(?:[.,/]\d+)?)?"
    rf"\s*(?:{_UNITS})\b\.?)",
    re.IGNORECASE,
)


SHOWS = ("tv_show", "podcast", "video_channel")
# A time in an episode: 12:34 or 1:02:03.
_CLOCK = re.compile(r"^(?:(\d{1,2}):)?(\d{1,3}):([0-5]\d)$")


class InvalidRecipe(ValueError):
    """The reason is written to be shown to the person entering the recipe."""


@dataclass
class EpisodeEntry:
    """Which episode of a show a recipe is in: any of its season and number,
    its title, or its address; and where in it, in seconds."""

    season: int | None = None
    number: int | None = None
    title: str | None = None
    url: str | None = None
    aired_on: date | None = None
    at_seconds: int | None = None


def seconds(clock: str | None) -> int | None:
    """A time in an episode, "12:34" or "1:02:03", as seconds; blank is None."""
    clock = (clock or "").strip()
    if not clock:
        return None
    found = _CLOCK.match(clock)
    hours, minutes, secs = found.groups() if found else (None, "60", "0")
    if not found or (hours is not None and int(minutes) > 59):
        raise InvalidRecipe("Give the time as minutes and seconds, like 12:34, or 1:02:03.")
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(secs)


def clock(at: int) -> str:
    """Seconds as a time in an episode: 12:34, or 1:02:03."""
    hours, rest = divmod(at, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def episode_name(season: int | None, number: int | None, title: str | None) -> str:
    """How an episode reads: Season 2, episode 5, “Fat”; or a video's title."""
    parts = []
    if number is not None:
        parts.append(
            f"Season {season}, episode {number}" if season is not None else f"Episode {number}"
        )
    if title:
        parts.append(f"“{title}”")
    return ", ".join(parts) or "A video"


@dataclass
class RecipeEntry:
    title: str
    # edition ID -> page, or None for "in this edition, page not recorded"
    pages: dict[uuid.UUID, str | None]
    lines: list[str]
    # For a website's recipe instead: the page's address, as web.page keeps it.
    web_address: str | None = None
    # For a magazine's or newspaper's: the issue, named as the cover names it
    # or by its date, and the page in it.
    issue: str | None = None
    issue_date: date | None = None
    issue_page: str | None = None
    # For a TV show's, podcast's or video channel's: the episode.
    episode: EpisodeEntry | None = None


def _squash(text: str) -> str:
    return " ".join(text.split())


def clean(
    title: str,
    pages: list[tuple[uuid.UUID, str | None]],
    lines: list[str],
    web_address: str | None = None,
    issue: str | None = None,
    issue_date: date | None = None,
    issue_page: str | None = None,
    episode: EpisodeEntry | None = None,
) -> RecipeEntry:
    """Normalise what was typed, or raise InvalidRecipe. Which of pages or
    web_address the recipe needs depends on its source (create, replace)."""
    title = _squash(title)
    if not title:
        raise InvalidRecipe("Give the recipe its title as the book prints it.")
    if len(title) > MAX_TITLE:
        raise InvalidRecipe(f"Titles are at most {MAX_TITLE} characters.")

    label = _squash(issue or "") or (issue_date.isoformat() if issue_date else None)
    if label and len(label) > MAX_TITLE:
        raise InvalidRecipe(f"An issue's name is at most {MAX_TITLE} characters.")
    in_issue = _squash(issue_page or "") or None
    if in_issue and len(in_issue) > MAX_PAGE:
        raise InvalidRecipe(f"A page is at most {MAX_PAGE} characters, like 112 or xii.")
    episode = _clean_episode(episode)
    if sum(bool(p) for p in (label, pages, web_address and web_address.strip(), episode)) > 1:
        raise InvalidRecipe(
            "A recipe is in one place: an edition, a web page, an issue or an episode."
        )
    url = None
    if web_address and web_address.strip():
        try:
            url, _ = web.page(web_address)
        except web.BadAddress as exc:
            raise InvalidRecipe(str(exc)) from None
    cleaned_pages: dict[uuid.UUID, str | None] = {}
    for edition_id, page in pages:
        if edition_id in cleaned_pages:
            raise InvalidRecipe("Each edition can be listed once.")
        page = _squash(page or "") or None
        if page and len(page) > MAX_PAGE:
            raise InvalidRecipe(f"A page is at most {MAX_PAGE} characters, like 112 or xii.")
        cleaned_pages[edition_id] = page

    kept = [_squash(line) for line in lines]
    # Each ingredient once per recipe (the entry rules), keeping the first;
    # the household index lists one twice in 288 recipes.
    seen: set[str] = set()
    kept = [
        line for line in kept if line and not (line.casefold() in seen or seen.add(line.casefold()))
    ]
    if len(kept) > MAX_LINES:
        raise InvalidRecipe(f"A recipe can have at most {MAX_LINES} ingredient lines.")
    for line in kept:
        if AMOUNT.match(line):
            raise InvalidRecipe(
                f"Leave out the amount in “{line}”. Just the ingredient, like “rhubarb”."
            )
        if len(line) > MAX_LINE:
            raise InvalidRecipe(
                f"An ingredient is at most {MAX_LINE} characters: its name, not the method."
            )
    return RecipeEntry(
        title=title,
        pages=cleaned_pages,
        lines=kept,
        web_address=url,
        issue=label,
        issue_date=issue_date,
        issue_page=in_issue if label else None,
        episode=episode,
    )


def _clean_episode(episode: EpisodeEntry | None) -> EpisodeEntry | None:
    """The episode as given, tidied; None when nothing names one."""
    if episode is None:
        return None
    title = _squash(episode.title or "") or None
    if title and len(title) > MAX_TITLE:
        raise InvalidRecipe(f"An episode's title is at most {MAX_TITLE} characters.")
    url = None
    if episode.url and episode.url.strip():
        try:
            url, _ = web.page(episode.url)
        except web.BadAddress as exc:
            raise InvalidRecipe(str(exc)) from None
    for n in (episode.season, episode.number):
        if n is not None and not 0 <= n <= 10_000:
            raise InvalidRecipe("Seasons and episodes are numbered from 0 to 10,000.")
    if episode.season is not None and episode.number is None:
        raise InvalidRecipe("Give the episode's number in its season too.")
    if episode.number is None and not title and not url:
        if episode.aired_on or episode.at_seconds is not None:
            raise InvalidRecipe("Say which episode: its number, its title or its address.")
        return None
    if episode.at_seconds is not None and episode.at_seconds >= 100 * 3600:
        raise InvalidRecipe("That time is longer than any episode.")
    return EpisodeEntry(
        season=episode.season,
        number=episode.number,
        title=title,
        url=url,
        aired_on=episode.aired_on,
        at_seconds=episode.at_seconds,
    )


async def _check_place(session: AsyncSession, source_id: uuid.UUID, entry: RecipeEntry) -> None:
    """A book's recipe is in its editions; a website's is on one of its
    pages. The database refuses a place in another source too, through the
    composite keys on recipe_locations; checking here turns that into a
    message rather than a 500."""
    source = await session.get_one(Source, source_id)
    if source.kind in SHOWS:
        if not entry.episode:
            raise InvalidRecipe("Say which episode the recipe is in: its number or its title.")
        if source.kind == "video_channel" and not entry.episode.url:
            raise InvalidRecipe("Give the video's address.")
        return
    if entry.episode:
        raise InvalidRecipe("Only a TV show, podcast or video channel has episodes.")
    if source.kind in ("magazine", "newspaper"):
        if not entry.issue:
            raise InvalidRecipe("Say which issue the recipe is in: its name or its date.")
        return
    if entry.issue:
        raise InvalidRecipe("Only a magazine or newspaper has issues.")
    if source.kind in ("packaging", "family"):
        if entry.pages or entry.web_address:
            where = "on packaging" if source.kind == "packaging" else "in a family collection"
            raise InvalidRecipe(f"A recipe {where} is just in it: no page or address.")
        return
    if source.kind in ("website", "social"):
        if not entry.web_address:
            raise InvalidRecipe("Give the web address of the recipe.")
        if source.kind == "website" and web.site(entry.web_address) != source.host:
            raise InvalidRecipe(f"That address isn't on {source.host}.")
        # A social media account's posts can be on any site, so one could
        # already be another account's; the database would refuse it too.
        elsewhere = await session.scalar(
            select(Source.title)
            .join(WebPage, WebPage.source_id == Source.id)
            .where(WebPage.url == entry.web_address, Source.id != source_id)
        )
        if elsewhere is not None:
            raise InvalidRecipe(f"That page is already one of {elsewhere}'s.")
        return
    if entry.web_address:
        raise InvalidRecipe("A book's recipe is in its editions, not on a web page.")
    if not entry.pages:
        raise InvalidRecipe("Say which edition the recipe is in.")
    known = set(
        (await session.scalars(select(Edition.id).where(Edition.source_id == source_id))).all()
    )
    if not set(entry.pages) <= known:
        raise InvalidRecipe("That edition isn't one of this book's.")


async def _episode(session: AsyncSession, source_id: uuid.UUID, given: EpisodeEntry) -> Episode:
    """The episode a recipe names: found by its address, then its number,
    then its title, with blanks filled in from what's given; or a new one."""
    here = Episode.source_id == source_id
    by_number = and_(
        here, Episode.number == given.number, Episode.season.is_not_distinct_from(given.season)
    )
    found = None
    if given.url:
        found = await session.scalar(select(Episode).where(here, Episode.url == given.url))
    if found is None and given.number is not None:
        found = await session.scalar(select(Episode).where(by_number))
    if found is None and given.title:
        found = await session.scalar(
            select(Episode)
            .where(here, func.lower(Episode.title) == given.title.lower())
            .order_by(Episode.created_at)
            .limit(1)
        )
    if found is None:
        found = Episode(
            source_id=source_id,
            season=given.season,
            number=given.number,
            title=given.title,
            url=given.url,
            aired_on=given.aired_on,
        )
        session.add(found)
        await session.flush()
        return found
    found.title = found.title or given.title
    found.aired_on = found.aired_on or given.aired_on
    if found.url is None and given.url:
        # No other episode has it: the search by address came first.
        found.url = given.url
    if found.number is None and given.number is not None:
        # Unless another episode has that number already.
        if await session.scalar(select(Episode.id).where(by_number)) is None:
            found.season, found.number = given.season, given.number
    return found


async def _write_parts(session: AsyncSession, recipe: Recipe, entry: RecipeEntry) -> None:
    if entry.episode:
        episode = await _episode(session, recipe.source_id, entry.episode)
        session.add(
            RecipeLocation(
                recipe_id=recipe.id,
                episode_id=episode.id,
                source_id=recipe.source_id,
                at_seconds=entry.episode.at_seconds,
            )
        )
    if entry.issue:
        # One row per issue: a recipe names it, and the first names it.
        found_issue = await session.scalar(
            select(Issue).where(
                Issue.source_id == recipe.source_id,
                func.lower(Issue.label) == entry.issue.lower(),
            )
        )
        if found_issue is None:
            found_issue = Issue(
                source_id=recipe.source_id, label=entry.issue, published_on=entry.issue_date
            )
            session.add(found_issue)
            await session.flush()
        elif found_issue.published_on is None and entry.issue_date:
            found_issue.published_on = entry.issue_date
        session.add(
            RecipeLocation(
                recipe_id=recipe.id,
                issue_id=found_issue.id,
                source_id=recipe.source_id,
                page=entry.issue_page,
            )
        )
    if entry.web_address:
        # One row per address: several recipes can share a page.
        found = await session.scalar(select(WebPage).where(WebPage.url == entry.web_address))
        if found is None:
            found = WebPage(source_id=recipe.source_id, url=entry.web_address)
            session.add(found)
            await session.flush()
        session.add(
            RecipeLocation(recipe_id=recipe.id, web_page_id=found.id, source_id=recipe.source_id)
        )
    for edition_id, page in entry.pages.items():
        session.add(
            RecipeLocation(
                recipe_id=recipe.id, edition_id=edition_id, source_id=recipe.source_id, page=page
            )
        )
    for position, line in enumerate(entry.lines, start=1):
        session.add(RecipeIngredient(recipe_id=recipe.id, position=position, original_text=line))
    await session.flush()


async def create(session: AsyncSession, source_id: uuid.UUID, entry: RecipeEntry) -> Recipe:
    await _check_place(session, source_id, entry)
    recipe = Recipe(source_id=source_id, title=entry.title)
    session.add(recipe)
    await session.flush()
    await _write_parts(session, recipe, entry)
    return recipe


async def replace(session: AsyncSession, recipe: Recipe, entry: RecipeEntry) -> None:
    """Make the recipe what the entry says: its pages and lines are rewritten.

    Rewriting lines drops anything hung off them (ingredient options). Until
    matching exists there is nothing to drop; when it does, editing will
    have to keep a line's matches when its text is unchanged.
    """
    await _check_place(session, recipe.source_id, entry)
    recipe.title = entry.title
    await session.execute(delete(RecipeLocation).where(RecipeLocation.recipe_id == recipe.id))
    await session.execute(delete(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id))
    await _write_parts(session, recipe, entry)
