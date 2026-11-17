"""The rules that suggest equipment (equipment_rules.py), on values: what a
title, a tag and a source each suggest, and what they don't. What happens
to a suggestion is routers/suggestions.py's, and tested there."""

import pytest
from sqlalchemy import text

from openlarder import equipment_rules as rules


@pytest.mark.parametrize(
    ("title", "things"),
    [
        ("Peach Gelato", ["Ice cream maker"]),
        ("Vanilla Ice Cream", ["Ice cream maker"]),
        ("Three Sorbets", ["Ice cream maker"]),
        ("Buttermilk Waffles", ["Waffle iron"]),
        ("WAFFLE", ["Waffle iron"]),
        ("Sous Vide Short Ribs", ["Sous vide circulator"]),
        ("Sous-Vide Eggs", ["Sous vide circulator"]),
        ("Smoked Brisket", ["Smoker"]),
        ("Grilled Corn", ["Grill"]),
        ("Lemon Bundt Cake", ["Bundt pan"]),
        ("Slow Cooker Chili", ["Slow cooker"]),
        ("Slow-Cooker Chili", ["Slow cooker"]),
        ("Instant Pot Risotto", ["Multicooker"]),
        ("Pressure Cooker Beans", ["Pressure cooker"]),
        ("Air Fryer Wings", ["Air fryer"]),
        ("Air-fryer wings", ["Air fryer"]),
        ("Canned Peaches", ["Canning pot"]),
        ("Strawberry Preserves", ["Canning pot"]),
        ("Fresh Pasta", ["Pasta machine"]),
        # Several at once, in the rules' order.
        ("Smoked and Grilled Ribs", ["Smoker", "Grill"]),
        # Not a whole word, or not these words.
        ("Waffled Hash Browns", []),
        ("Smoker's Stew", []),
        ("Grilling Sauce", []),
        ("Pasta with Fresh Tomatoes", []),
        ("Preserved Lemons", []),
        ("Scream Cheese Dip", []),
        ("Roast Chicken", []),
        ("", []),
    ],
)
def test_what_a_title_suggests(title: str, things: list[str]) -> None:
    assert list(rules.suggested(title)) == things


def test_a_rule_is_sometimes_wrong_which_is_why_its_reviewed() -> None:
    """The spec's own example: nothing here knows a grilled cheese is made
    in a pan. It's suggested, and a moderator says no."""
    assert list(rules.suggested("Grilled Cheese")) == ["Grill"]
    assert list(rules.suggested("Smoked Paprika Chicken")) == ["Smoker"]


def test_why_is_said_and_the_title_says_it_first() -> None:
    assert rules.suggested("Peach Gelato") == {"Ice cream maker": "Its title says “gelato”."}
    assert rules.suggested("Ribs", tags=["Smoking", "Main"]) == {"Smoker": "It is tagged Smoking."}
    assert rules.suggested("Ribs", source_tags=["Grilling"]) == {
        "Grill": "Its source is tagged Grilling."
    }
    assert rules.suggested("Chili", source_title="The Slow Cooker Bible") == {
        "Slow cooker": "Its source's title says “slow cooker”."
    }
    # One thing, said four ways: the recipe's own title is the reason.
    every = rules.suggested(
        "Slow Cooker Chili",
        tags=["Slow Cooker"],
        source_title="Slow Cooker Revolution",
        source_tags=["Slow Cooker"],
    )
    assert every == {"Slow cooker": "Its title says “slow cooker”."}
    # Then its own tag, before its source's.
    assert rules.suggested("Chili", tags=["Slow Cooker"], source_tags=["Slow Cooker"]) == {
        "Slow cooker": "It is tagged Slow Cooker."
    }


@pytest.mark.parametrize(
    ("source", "things"),
    [
        ("The Instant Pot Bible", ["Multicooker"]),
        ("Multicooker Perfection", ["Multicooker"]),
        ("Air Fryer Perfection", ["Air fryer"]),
        ("The Bread Machine Cookbook", ["Bread machine"]),
        ("Sous Vide at Home", ["Sous vide circulator"]),
        ("Pressure Cooker Perfection", ["Pressure cooker"]),
        # A book about a dish, or a way of cooking, isn't about one appliance.
        ("Ice Cream", []),
        ("The Grilling Book", []),
        ("Waffles and Pancakes", []),
        ("Plenty", []),
    ],
)
def test_what_a_books_title_suggests_for_every_recipe_in_it(source: str, things: list[str]) -> None:
    assert list(rules.suggested("Plain Rice", source_title=source)) == things


def test_a_tag_that_isnt_named_for_a_thing_suggests_nothing() -> None:
    assert rules.suggested("Stew", tags=["Braising", "Baking", "Main", "Vegan"]) == {}
    # By its whole name, not a word of it.
    assert rules.suggested("Stew", tags=["Slow"]) == {}


async def test_every_thing_the_rules_name_is_in_the_equipment_list(adb) -> None:
    """The names are the list's as seeded: a rule naming nothing would
    suggest nothing, silently."""
    named = {thing for thing, _ in (*rules.TITLE, *rules.SOURCE)} | set(rules.TAGS.values())
    listed = set(
        await adb.scalars(
            text("SELECT name FROM equipment WHERE listed AND NOT assumed AND name = ANY(:n)"),
            {"n": sorted(named)},
        )
    )
    assert named - listed == set()
    tags = set(
        await adb.scalars(
            text("SELECT name FROM tags WHERE name = ANY(:n)"), {"n": sorted(rules.TAGS)}
        )
    )
    assert set(rules.TAGS) - tags == set()
