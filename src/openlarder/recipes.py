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

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.models import Edition, Recipe, RecipeIngredient, RecipePage

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


class InvalidRecipe(ValueError):
    """The reason is written to be shown to the person entering the recipe."""


@dataclass
class RecipeEntry:
    title: str
    # edition ID -> page, or None for "in this edition, page not recorded"
    pages: dict[uuid.UUID, str | None]
    lines: list[str]


def _squash(text: str) -> str:
    return " ".join(text.split())


def clean(title: str, pages: list[tuple[uuid.UUID, str | None]], lines: list[str]) -> RecipeEntry:
    """Normalise what was typed, or raise InvalidRecipe."""
    title = _squash(title)
    if not title:
        raise InvalidRecipe("Give the recipe its title as the book prints it.")
    if len(title) > MAX_TITLE:
        raise InvalidRecipe(f"Titles are at most {MAX_TITLE} characters.")

    if not pages:
        raise InvalidRecipe("Say which edition the recipe is in.")
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
    return RecipeEntry(title=title, pages=cleaned_pages, lines=kept)


async def _check_editions(session: AsyncSession, work_id: uuid.UUID, entry: RecipeEntry) -> None:
    # The database refuses a page in another book's edition too, through the
    # composite keys on recipe_pages; checking here turns that into a
    # message rather than a 500.
    known = set((await session.scalars(select(Edition.id).where(Edition.work_id == work_id))).all())
    if not set(entry.pages) <= known:
        raise InvalidRecipe("That edition isn't one of this book's.")


async def _write_parts(session: AsyncSession, recipe: Recipe, entry: RecipeEntry) -> None:
    for edition_id, page in entry.pages.items():
        session.add(
            RecipePage(
                recipe_id=recipe.id, edition_id=edition_id, work_id=recipe.work_id, page=page
            )
        )
    for position, line in enumerate(entry.lines, start=1):
        session.add(RecipeIngredient(recipe_id=recipe.id, position=position, original_text=line))
    await session.flush()


async def create(session: AsyncSession, work_id: uuid.UUID, entry: RecipeEntry) -> Recipe:
    await _check_editions(session, work_id, entry)
    recipe = Recipe(work_id=work_id, title=entry.title)
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
    await _check_editions(session, recipe.work_id, entry)
    recipe.title = entry.title
    await session.execute(delete(RecipePage).where(RecipePage.recipe_id == recipe.id))
    await session.execute(delete(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id))
    await _write_parts(session, recipe, entry)
