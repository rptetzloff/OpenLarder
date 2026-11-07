"""Recipe entries: a title, a page per edition, and ingredient lines as printed.

What a recipe entry may hold is the content rule's: facts, never the
method or the headnote. So there is no free-text field beyond the
ingredient lines, which are kept exactly as the book prints them; matching
them to canonical ingredients is a later step and changes nothing typed.

A recipe appears in the editions listed for it. A page left blank means it
is in that edition but the page isn't recorded yet; an edition not listed
means the recipe isn't in it. *That settles the open question in SCOPING
of an edition whose page is unknown; chosen by Claude, 2026-11-07, as the
model's docstring already described.*
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.models import Edition, Recipe, RecipeIngredient, RecipePage

MAX_TITLE = 200
MAX_PAGE = 20
MAX_LINE = 300
MAX_LINES = 150


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
    kept = [line for line in kept if line]
    if len(kept) > MAX_LINES:
        raise InvalidRecipe(f"A recipe can have at most {MAX_LINES} ingredient lines.")
    if any(len(line) > MAX_LINE for line in kept):
        raise InvalidRecipe(
            f"An ingredient line is at most {MAX_LINE} characters. The method doesn't go here."
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
