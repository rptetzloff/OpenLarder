"""Ingredients that count as another by their names: suggestions for a
moderator, never a parent set unasked.

On 2026-11-17 the live catalog had 6,947 ingredients and 6 of them counted
as another, so a search for cheese missed Goat Cheese, Blue Cheese and 47
more that end with the word. A name that ends with another ingredient's
whole name is often a kind of it ("Goat Cheese", "Cheese"), and often
isn't: Almond Butter is not butter, Coconut Milk is not milk, Dr Pepper
is not pepper, and 199 things end with "Powder". Taken by name alone that
was 4,464 suggestions, many wrong, and a wrong one passes an allergen
down.

So only the families listed here (FAMILIES), each a head ingredient whose
name can be trusted to mean one food, and each with the words that leave
a name out of it. *Ray, 2026-11-17*, asked how to go about it: a list he
approves; shown the list, with every member and everything left out, from
that day's public dump: "looks good". The list and its leavings-out were
Claude's to draw up, and the calls in it Ray was asked about by name are
marked below. What isn't here was refused or not looked at: Powder,
Paste, Juice, Sauce, Seeds, Oil, Pepper, Butter, Milk, Cream, Flour,
Beans, Peas, Nuts, the cuts of meat, and more. Some of those have a
narrower family that is here (Olive Oil, Soy Sauce, Chili Powder, Wheat
Flour).

The test of a family: where a recipe says only the head ("cheese",
"onion", "vinegar"), any member would do, and someone searching for the
head wants the members' recipes.

Left out of every family: a name that is two things ("Anchovy in Olive
Oil", "Rice Vinegar and Balsamic Vinegar"), and a stand-in for the thing
("Dairy-Free Cheese", "Imitation Crab", "Other Chile"), which is exactly
what must not inherit from it. For a fruit or a vegetable, only as it
grows (KEPT): dried, pickled, candied or ground, it is something else in
the kitchen. A dried herb is the herb, and a dried chile a chile.

A member counts as the nearest of its family that its name ends with:
Sharp Cheddar Cheese as Cheddar Cheese, and that as Cheese.

What this can't see: a member whose name doesn't end with the head
(Parmesan, Scallion), which Wikidata's "subclass of" may (wikidata_names
.py); a head spelt two ways ("Chile" and "Chili" are two families); a
name that's a typo. Each goes to the Suggestions queue (routers/
suggestions.py) as any "counts as" suggestion does: accepted, it's the
moderator's edit; dismissed, it isn't suggested again.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import visibility
from openlarder.models import Ingredient, Suggestion

MODEL = "rules"
VERSION = "name-families-v1"
KIND = "parent"

# A name with one of these before its head is two things.
JOINING = frozenset({"in", "with", "and", "or", "of", "from", "plus", "without"})
MARKS = (",", "/", "=", "(", ")")
# And with one of these, or a word ending "-free", a stand-in for it.
STANDING_IN = frozenset({"other", "leftover", "imitation", "vegan", "non-dairy", "nondairy"})
# A fruit or a vegetable is in its family only as it grows.
KEPT = frozenset(
    {
        "dried", "freeze-dried", "spray-dried", "oven-dried", "sun-dried", "semi-dried",
        "semidried", "pickled", "candied", "crystallized", "powdered", "ground", "granulated",
        "frozen", "canned", "preserved", "oil-packed", "smoked", "roasted", "creamed",
        "fermented", "salted", "puffed",
    }
)  # fmt: skip
# A name that is also what something else is called. Pink salt is sold as
# a finishing salt and is what curers call curing salt, which has nitrite
# in it.
ALSO_CALLED = frozenset({"pink salt"})

# Each head, and the words that leave a name out of its family.
FAMILIES: dict[str, frozenset[str]] = {
    # Fruit and vegetables, as they grow. A green or spring onion is a
    # scallion; a sweet potato isn't a potato; sea lettuce is a seaweed;
    # black garlic is fermented. A dried chile is still a chile (Ray was
    # asked), ground it is a powder.
    "Onion": KEPT | {"green", "spring"},
    "Apple": KEPT,
    "Pear": KEPT,
    "Fig": KEPT,
    "Plum": KEPT,
    "Orange": KEPT | {"lemon"},
    "Potato": KEPT | {"sweet"},
    "Tomato": KEPT,
    "Mushroom": KEPT,
    "Squash": KEPT,
    "Lettuce": KEPT | {"sea"},
    "Cabbage": KEPT,
    "Cucumber": KEPT | {"distilled"},
    "Radish": KEPT,
    "Greens": KEPT,
    "Garlic": KEPT | {"black", "chile"},
    "Ginger": KEPT,
    "Chile": frozenset({"pickled", "ground"}),
    # Herbs and spices: dried is how most recipes mean them.
    "Basil": frozenset(),
    "Oregano": frozenset(),
    "Sage": frozenset(),
    "Chives": frozenset(),
    "Paprika": frozenset(),
    "Peppercorns": frozenset(),
    "Chili Powder": frozenset(),
    "Chile Powder": frozenset(),
    "Curry Powder": frozenset({"milk"}),
    # Dairy. Cream cheese, cottage cheese and ricotta are cheese (Ray was
    # asked). Frozen yogurt is a dessert; coconut and soy aren't dairy.
    "Cheese": frozenset(),
    "Cheddar": frozenset(),
    "Yogurt": frozenset({"frozen", "coconut", "soy"}),
    # The cupboard. Flavored oils and salts are seasonings of their own.
    # Curing salt has nitrite in it and must never stand in for salt. Dry
    # mustard is a powder, sea mustard a seaweed. White chocolate has no
    # cocoa solids. Cauliflower rice is cauliflower; wild rice is rice,
    # and brown, coconut, maple and palm sugar are sugar (Ray was asked).
    "Vinegar": frozenset({"spray-dried", "mother"}),
    "Olive Oil": frozenset(
        {"truffle", "garlic-flavored", "garlic-infused", "lemon-infused", "lemon-scented"}
    ),
    "Sesame Oil": frozenset(),
    "Salt": frozenset(
        {
            "curing",
            "aquarium",
            "celery",
            "garlic",
            "onion",
            "truffle",
            "bay",
            "seasoned",
            "seasoning",
            "pickling",
        }
    ),  # fmt: skip
    "Sugar": frozenset({"cinnamon", "vanilla", "priming", "decorating"}),
    "Honey": frozenset({"spray-dried", "granulated"}),
    "Mustard": frozenset({"dry", "dried", "ground", "powdered", "colman's", "sea", "spinach"}),
    "Miso": frozenset(),
    "Soy Sauce": frozenset(),
    "Hot Sauce": frozenset(),
    "Chocolate": frozenset({"white"}),
    "Rice": frozenset({"cauliflower", "puffed", "yeast"}),
    "Noodles": frozenset({"butternut", "parsnip", "zucchini", "kelp", "wakame"}),
    "Pasta": frozenset(),
    "Bread": frozenset(),
    "Oats": frozenset({"puffed"}),
    "Lentils": frozenset({"puffed"}),
    "Wheat Flour": frozenset(),
    "Rye Flour": frozenset(),
    "Rice Flour": frozenset({"wild"}),
    "Tofu": frozenset(),
    "Stock": frozenset(),
    "Coconut": frozenset(),
    # Meat and fish. Cured beef isn't what a recipe means by beef.
    "Beef": frozenset({"corned", "air-dried", "dried", "deli"}),
    "Pork": frozenset({"salt", "wrapper"}),
    "Chicken": frozenset({"liquid"}),
    "Sausage": frozenset(),
    "Bacon": frozenset(),
    "Ham": frozenset(),
    "Chorizo": frozenset(),
    "Shrimp": KEPT,
    "Tuna": frozenset({"oil-packed"}),
    # Drinks. Port, Madeira and Marsala are wine; rice wine and cooking
    # wine don't stand in for it. Ginger beer and root beer are soft
    # drinks. Herbal teas are tea (Ray was asked).
    "Wine": frozenset({"rice", "shaoxing", "chinese", "cooking"}),
    "Beer": frozenset({"ginger", "root"}),
    "Rum": frozenset(),
    "Whiskey": frozenset(),
    "Sherry": frozenset(),
    "Tea": frozenset(),
    "Coffee": frozenset({"distilled"}),
}


def left_out(name: str, head: str) -> bool:
    """Whether a name ending with a family's head is left out of it."""
    folded = name.casefold()
    if folded in ALSO_CALLED:
        return True
    before = folded[: -len(head)].strip()
    words = before.split()
    if any(mark in before for mark in MARKS):
        return True
    return any(
        w in JOINING or w in STANDING_IN or w.endswith("-free") or w in FAMILIES[head]
        for w in words
    )


def found(names: Iterable[str]) -> dict[str, tuple[str, str]]:
    """Of these ingredients' names, each that counts as another by these
    rules: its name, with the name it counts as and its family's head, as
    each is written among them. A head that isn't among them has no
    family."""
    written = {name.casefold(): name for name in names}
    out: dict[str, tuple[str, str]] = {}
    for head in FAMILIES:
        ending = " " + head.casefold()
        if head.casefold() not in written:
            continue
        family = {
            folded
            for folded, name in written.items()
            if folded.endswith(ending) and not left_out(name, head)
        }
        for folded in family:
            words = folded.split()
            # The nearest of the family it ends with, or the head.
            nearest = next(
                tail
                for start in range(1, len(words))
                if (tail := " ".join(words[start:])) in family or tail == head.casefold()
            )
            out[written[folded]] = (written[nearest], written[head.casefold()])
    return out


def pair(a: uuid.UUID, b: uuid.UUID) -> list[str]:
    """The queue's target for two ingredients: the two ids, the lower first."""
    return sorted([str(a), str(b)])


async def sweep(session: AsyncSession) -> int:
    """Add a suggestion for each ingredient these rules say counts as
    another; how many were new. The caller commits.

    Only ingredients anyone can see: one only a private recipe uses never
    reaches the queue, as a member or as a head. Not one that counts as
    something already: someone has said what. And not a pair already
    suggested, by these rules or anything else: open, it's there; accepted
    or dismissed, it's been decided."""
    rows = {
        name: (ingredient_id, parent_id)
        for ingredient_id, name, parent_id in await session.execute(
            select(Ingredient.id, Ingredient.name, Ingredient.parent_id).where(
                visibility.ingredients_seen_by(None)
            )
        )
    }
    known = {
        tuple(target)
        for (target,) in await session.execute(
            select(Suggestion.target).where(Suggestion.kind == KIND)
        )
    }
    new = 0
    for name, (above, head) in sorted(found(rows).items()):
        ingredient_id, parent_id = rows[name]
        if parent_id is not None:
            continue
        target = pair(ingredient_id, rows[above][0])
        if tuple(target) in known:
            continue
        # ON CONFLICT for two sweeps at once: one open suggestion a pair.
        filed = await session.execute(
            insert(Suggestion)
            .values(
                kind=KIND,
                target=target,
                proposal={
                    "a_id": str(ingredient_id),
                    "b_id": str(rows[above][0]),
                    "a_name": name,
                    "b_name": above,
                    "decision": "a_under_b",
                    "certainty": "likely",
                    "family_id": str(rows[head][0]),
                    "family_name": head,
                },
                reason=f"Its name ends with “{above}”, one of the {head} family.",
                model=MODEL,
                prompt_version=VERSION,
            )
            .on_conflict_do_nothing()
            .returning(Suggestion.id)
        )
        if filed.first() is not None:
            new += 1
    return new
