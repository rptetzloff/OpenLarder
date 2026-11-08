"""Substitutions: one ingredient or recipe standing in for another.

A swap goes one way ("coconut oil for butter"), for a diet or for none in
particular, and comes from a book (an edition and, usually, a page) or is
contributed. How much to use is a free-text note. See SCOPING,
"Substitutions".

Admins enter swaps from a recipe's page, where the book's edition and page
are filled in from the recipe, or from an ingredient's page. *Ray,
2026-11-08.* An ingredient's page lists the swaps for it; a recipe's page
lists the swaps for what it uses: its ingredients, the recipes its lines
cite, and the recipe itself (a flour blend another book's blend can
replace).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from openlarder.models import (
    Edition,
    Ingredient,
    IngredientOption,
    Recipe,
    Source,
    Substitution,
    Tag,
    TagKind,
)

MAX_NOTE = 300
MAX_PAGE = 20


class InvalidSwap(ValueError):
    """The reason is written to be shown beside the form."""


class AlreadyThere(ValueError):
    """The same swap, for the same diet, from the same source, exists."""


@dataclass
class Side:
    """An ingredient or a recipe; exactly one is set."""

    ingredient_id: uuid.UUID | None = None
    recipe_id: uuid.UUID | None = None


@dataclass
class SwapIn:
    instead_of: Side
    use: Side
    diet_id: uuid.UUID | None = None
    # None: contributed rather than printed.
    source_edition_id: uuid.UUID | None = None
    source_page: str | None = None
    note: str | None = None


def _squash(text: str | None) -> str | None:
    return " ".join((text or "").split()) or None


async def _check_side(session: AsyncSession, side: Side, which: str) -> None:
    if (side.ingredient_id is None) == (side.recipe_id is None):
        raise InvalidSwap(f"Choose one ingredient or one recipe {which}.")
    model, key = (
        (Ingredient, side.ingredient_id) if side.ingredient_id else (Recipe, side.recipe_id)
    )
    if await session.get(model, key) is None:
        raise InvalidSwap(f"The {model.__name__.lower()} {which} doesn't exist any more.")


async def add(session: AsyncSession, swap: SwapIn) -> Substitution:
    await _check_side(session, swap.instead_of, "to replace")
    await _check_side(session, swap.use, "to use instead")
    if (swap.instead_of.ingredient_id, swap.instead_of.recipe_id) == (
        swap.use.ingredient_id,
        swap.use.recipe_id,
    ):
        raise InvalidSwap("Something can't stand in for itself.")
    if swap.diet_id is not None:
        diet = await session.get(Tag, swap.diet_id)
        if diet is None or diet.kind != TagKind.DIET:
            raise InvalidSwap("That diet doesn't exist.")
    page = _squash(swap.source_page)
    if page and len(page) > MAX_PAGE:
        raise InvalidSwap(f"A page is at most {MAX_PAGE} characters.")
    if swap.source_edition_id is not None:
        if await session.get(Edition, swap.source_edition_id) is None:
            raise InvalidSwap("That edition doesn't exist.")
    elif page:
        raise InvalidSwap("A page needs the book it's in.")
    note = _squash(swap.note)
    if note and len(note) > MAX_NOTE:
        raise InvalidSwap(f"A note is at most {MAX_NOTE} characters.")

    row = Substitution(
        from_ingredient_id=swap.instead_of.ingredient_id,
        from_recipe_id=swap.instead_of.recipe_id,
        to_ingredient_id=swap.use.ingredient_id,
        to_recipe_id=swap.use.recipe_id,
        diet_tag_id=swap.diet_id,
        source_edition_id=swap.source_edition_id,
        source_page=page,
        note=note,
    )
    # uq_substitutions_swap would refuse it; said here so it can be said well.
    same = [
        getattr(Substitution, c).is_not_distinct_from(getattr(row, c))
        for c in (
            "from_ingredient_id",
            "from_recipe_id",
            "to_ingredient_id",
            "to_recipe_id",
            "diet_tag_id",
            "source_edition_id",
        )
    ]
    if await session.scalar(select(Substitution.id).where(*same)) is not None:
        raise AlreadyThere("That swap is here already.")
    session.add(row)
    await session.flush()
    return row


async def add_diet(session: AsyncSession, name: str) -> Tag:
    """A diet by this name, the existing one if there is one."""
    name = _squash(name) or ""
    if not name:
        raise InvalidSwap("Give the diet a name.")
    existing = await session.scalar(
        select(Tag).where(Tag.kind == TagKind.DIET, func.lower(Tag.name) == name.lower())
    )
    if existing is not None:
        return existing
    diet = Tag(kind=TagKind.DIET, name=name)
    session.add(diet)
    await session.flush()
    return diet


@dataclass
class Thing:
    kind: str  # "ingredient" or "recipe"
    id: uuid.UUID
    name: str


@dataclass
class Listed:
    id: uuid.UUID
    instead_of: Thing
    use: Thing
    diet: tuple[uuid.UUID, str] | None
    # (book ID, book title, edition ID, page) when printed in a book.
    source: tuple[uuid.UUID, str, uuid.UUID, str | None] | None
    note: str | None


async def listed(session: AsyncSession, *conditions: ColumnElement[bool]) -> list[Listed]:
    """The swaps meeting the conditions, by what they replace, then what
    stands in, with everything named."""
    fi, fr, ti, tr = (
        aliased(Ingredient),
        aliased(Recipe),
        aliased(Ingredient),
        aliased(Recipe),
    )
    instead_name = func.coalesce(fi.name, fr.title)
    use_name = func.coalesce(ti.name, tr.title)
    rows = await session.execute(
        select(
            Substitution,
            instead_name,
            use_name,
            Tag.name,
            Source.id,
            Source.title,
        )
        .outerjoin(fi, fi.id == Substitution.from_ingredient_id)
        .outerjoin(fr, fr.id == Substitution.from_recipe_id)
        .outerjoin(ti, ti.id == Substitution.to_ingredient_id)
        .outerjoin(tr, tr.id == Substitution.to_recipe_id)
        .outerjoin(Tag, Tag.id == Substitution.diet_tag_id)
        .outerjoin(Edition, Edition.id == Substitution.source_edition_id)
        .outerjoin(Source, Source.id == Edition.source_id)
        .where(*conditions)
        .order_by(func.lower(instead_name), func.lower(use_name), Substitution.id)
    )
    out = []
    for s, instead, use, diet, source_id, source_title in rows:
        out.append(
            Listed(
                id=s.id,
                instead_of=_thing(s.from_ingredient_id, s.from_recipe_id, instead),
                use=_thing(s.to_ingredient_id, s.to_recipe_id, use),
                diet=(s.diet_tag_id, diet) if s.diet_tag_id else None,
                source=(
                    (source_id, source_title, s.source_edition_id, s.source_page)
                    if s.source_edition_id
                    else None
                ),
                note=s.note,
            )
        )
    return out


def _thing(ingredient_id: uuid.UUID | None, recipe_id: uuid.UUID | None, name: str) -> Thing:
    if ingredient_id is not None:
        return Thing("ingredient", ingredient_id, name)
    assert recipe_id is not None  # one_from and one_to make one side set
    return Thing("recipe", recipe_id, name)


def for_recipe(recipe_id: uuid.UUID) -> ColumnElement[bool]:
    """Swaps for what a recipe uses, and for the recipe itself."""
    options = select(IngredientOption).where(IngredientOption.recipe_id == recipe_id).subquery()
    return or_(
        Substitution.from_ingredient_id.in_(
            select(options.c.ingredient_id).where(options.c.ingredient_id.is_not(None))
        ),
        Substitution.from_recipe_id.in_(
            select(options.c.sub_recipe_id).where(options.c.sub_recipe_id.is_not(None))
        ),
        Substitution.from_recipe_id == recipe_id,
    )
