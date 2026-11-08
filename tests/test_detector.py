"""The entry rules on one line: what's wrong, and the bare ingredient."""

import pytest

from fake_broker import _sign_in
from openlarder import detector
from openlarder.detector import AMOUNT, LEFT_OUT, OPTIONAL, PREP, TWICE, review, review_all


@pytest.mark.parametrize(
    "line, suggestion",
    [
        # The examples in issue #26.
        ("two eggs", "eggs"),
        ("half a lemon", "lemon"),
        ("a handful of basil", "basil"),
        ("cup of milk", "milk"),
        ("tbsp olive oil", "olive oil"),
        ("3 large eggs", "eggs"),
        ("a lemon", "lemon"),
        ("an apple", "apple"),
        ("2 cloves of garlic", "garlic"),
        ("Twelve Oysters", "Oysters"),
    ],
)
def test_an_amount_is_left_out(line, suggestion) -> None:
    assert review(line) == detector.Review(problems=[AMOUNT], suggestion=suggestion)


@pytest.mark.parametrize(
    "line, suggestion",
    [
        ("onions, finely diced", "onions"),
        ("butter, softened", "butter"),
        ("Butter, at room temperature", "Butter"),
        ("finely chopped onion", "onion"),
        ("Parsley, for garnish", "Parsley"),
        ("Flour, plus more for dusting", "Flour"),
        ("Lemon Zest to taste", "Lemon Zest"),
        ("Carrot, cut into coins", "Carrot"),
        ("freshly ground nutmeg", "nutmeg"),
    ],
)
def test_prep_and_serving_notes_are_left_out(line, suggestion) -> None:
    assert review(line) == detector.Review(problems=[PREP], suggestion=suggestion)


def test_both_at_once() -> None:
    assert review("2 onions, finely diced") == detector.Review(
        problems=[AMOUNT, PREP], suggestion="onions"
    )


def test_each_option_is_trimmed_and_a_reference_kept() -> None:
    found = review("2 eggs, beaten or Flax Egg (p. 12) or 1 banana")
    assert found.suggestion == "eggs, Flax Egg (p. 12), or banana"
    assert review("Eggs, beaten or Flax Egg").suggestion == "Eggs or Flax Egg"


def test_a_problem_is_named_once_however_many_options_have_it() -> None:
    assert review("2 eggs or 3 bananas").problems == [AMOUNT]


@pytest.mark.parametrize(
    "line",
    [
        "Salt",
        "a pinch of salt",
        "Salt, to taste",
        "Kosher Salt",
        "Freshly Ground Black Pepper",
        "Ground Black Pepper",
        "Granulated Sugar",
        "boiling water",
        "Salt & Pepper",
    ],
)
def test_the_stop_list_is_left_out(line) -> None:
    assert review(line) == detector.Review(problems=[LEFT_OUT], remove=True)


@pytest.mark.parametrize("line", ["Pecans (optional)", "Chives, if desired", "Capers if using"])
def test_optional_items_are_left_out(line) -> None:
    assert review(line) == detector.Review(problems=[OPTIONAL], remove=True)


@pytest.mark.parametrize(
    "line",
    [
        # Special kinds, and choices, aren't the stop list.
        "Sea Salt",
        "White Pepper",
        "Brown Sugar",
        "Coconut Water",
        "Sugar or Honey",
        # Names that look like amounts or prep, from the household index.
        "Half-and-Half",
        "Five-Spice Powder",
        "Five Spice Powder",
        "160 Bloom Gelatin",
        "00 Flour",
        "2% Milk",
        "7-Minute Frosting",
        "7 Minute Frosting",
        "80 Proof Vodka",
        "Diced Tomato (Can)",
        "Shredded Coconut",
        "Ground Cloves",
        "Cinnamon, Mace, Ground Cloves",
        "Large Shrimp",
        "Clove Essential Oil",
        "Head of Small Fish",
        "Lettuce Cup",
        "Some Kind of Cheese",
        "Basic Cauli-Rice (p. 269)",
        # Nothing but prep: no ingredient to suggest.
        ", softened",
        "",
        "   ",
    ],
)
def test_ingredients_pass(line) -> None:
    assert review(line) == detector.Review()


def test_a_line_repeated_is_marked_to_go() -> None:
    found = review_all(["Butter", "Egg", "butter", "Eggs", "2 eggs", "", "", "Salt", "Salt"])
    assert [(r.problems, r.remove) for r in found] == [
        ([], False),
        ([], False),
        ([TWICE], True),
        ([TWICE], True),
        ([TWICE], True),
        ([], False),
        ([], False),
        ([LEFT_OUT], True),
        # Left out for the rule, not as a repeat.
        ([LEFT_OUT], True),
    ]


# The form's check


async def test_the_form_can_check_its_lines(client, broker) -> None:
    await _sign_in(client, broker)
    response = await client.post(
        "/api/ingredient-lines/check", json={"lines": ["2 eggs", "Rhubarb", "Salt", "rhubarb"]}
    )
    assert response.json() == {
        "lines": [
            {"problems": [AMOUNT], "suggestion": "eggs", "remove": False},
            {"problems": [], "suggestion": None, "remove": False},
            {"problems": [LEFT_OUT], "suggestion": None, "remove": True},
            {"problems": [TWICE], "suggestion": None, "remove": True},
        ]
    }


async def test_checking_needs_someone_signed_in(client) -> None:
    response = await client.post("/api/ingredient-lines/check", json={"lines": ["2 eggs"]})
    assert response.status_code == 401
