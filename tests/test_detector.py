"""The entry rules on one line: what's wrong, and the bare ingredient."""

import pytest
from sqlalchemy import text

from fake_broker import _sign_in, make_admins
from openlarder import detector
from openlarder.detector import AMOUNT, LEFT_OUT, OPTIONAL, PREP, TWICE, review, review_all
from openlarder.ingredients import match_key


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
    reviews = response.json()["lines"]
    assert [{k: r[k] for k in ("problems", "suggestion", "remove")} for r in reviews] == [
        {"problems": [AMOUNT], "suggestion": "eggs", "remove": False},
        {"problems": [], "suggestion": None, "remove": False},
        {"problems": [LEFT_OUT], "suggestion": None, "remove": True},
        {"problems": [TWICE], "suggestion": None, "remove": True},
    ]
    # Saving would refuse none of these; it does refuse an amount with a unit.
    assert [r["refused"] for r in reviews] == [False] * 4
    # Only a line the rules are happy with is read into its options.
    assert [[o["name"] for o in r["options"]] for r in reviews] == [[], ["Rhubarb"], [], []]


async def test_checking_needs_someone_signed_in(client) -> None:
    response = await client.post("/api/ingredient-lines/check", json={"lines": ["2 eggs"]})
    assert response.status_code == 401


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


async def _ingredient(adb, name, *aliases):
    found = await adb.scalar(
        text("INSERT INTO ingredients (name, match_key) VALUES (:n, :k) RETURNING id"),
        {"n": name, "k": match_key(name)},
    )
    for alias in aliases:
        await adb.execute(
            text(
                "INSERT INTO ingredient_aliases (ingredient_id, name, match_key)"
                " VALUES (:i, :n, :k)"
            ),
            {"i": found, "n": alias, "k": match_key(alias)},
        )
    return str(found)


def _read(response):
    assert response.status_code == 200, response.text
    return [r["options"] for r in response.json()["lines"]]


async def test_the_check_says_what_each_line_will_be_matched_to(admin, adb) -> None:
    onion = await _ingredient(adb, "Green Onion", "Scallions")
    rice = await _ingredient(adb, "Glutinous Rice Flour", "Sweet Rice Flour")
    lines = ["green onions", "scallion", "sweet rice flower", "frog's legs"]
    read = _read(await admin.post("/api/ingredient-lines/check", json={"lines": lines}))
    assert [(o[0]["ingredient"], o[0]["alias"]) for o in read] == [
        ({"id": onion, "name": "Green Onion"}, False),
        ({"id": onion, "name": "Green Onion"}, True),
        (None, False),
        (None, False),
    ]
    # Nothing has that name, but one is called something like it.
    assert read[2][0]["similar"] == [{"id": rice, "name": "Glutinous Rice Flour"}]
    assert read[3][0]["similar"] == []


async def test_each_option_is_read(admin, adb) -> None:
    oil = await _ingredient(adb, "Grapeseed Oil")
    read = _read(
        await admin.post(
            "/api/ingredient-lines/check", json={"lines": ["grapeseed oil or olive oil"]}
        )
    )
    assert [(o["name"], o["ingredient"] and o["ingredient"]["id"]) for o in read[0]] == [
        ("grapeseed oil", oil),
        ("olive oil", None),
    ]


async def test_a_page_reference_names_the_recipe_in_the_source(admin, adb) -> None:
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Gluten-Free') RETURNING id"))
    edition = await adb.scalar(
        text("INSERT INTO editions (source_id) VALUES (:s) RETURNING id"), {"s": book}
    )
    added = await admin.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Biscuit Blend",
            "editions": [{"edition_id": str(edition), "page": "14"}],
            "ingredients": ["rice flour"],
        },
    )
    blend = added.json()["id"]
    # A second recipe on page 14, so a reference to it by another name is
    # ambiguous and stays unlinked.
    curd = await admin.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Lemon Curd",
            "editions": [{"edition_id": str(edition), "page": "14"}],
            "ingredients": ["lemons"],
        },
    )
    assert curd.status_code == 201, curd.text
    lines = ["Biscuit Blend (p. 14)", "Mystery Mix (p. 99)", "Shortbread (p. 14)"]
    body = {"lines": lines, "source_id": str(book)}
    read = _read(await admin.post("/api/ingredient-lines/check", json=body))
    assert read[0][0]["recipe"] == {"id": blend, "name": "Biscuit Blend"}
    assert read[0][0]["recipe_pages"] == ["14"]
    assert read[1][0]["recipe"] is None
    assert not read[1][0]["page_used"]
    # Page 14 has a recipe, just not that one.
    assert read[2][0]["recipe"] is None and read[2][0]["page_used"]
    # A component is never an ingredient.
    assert read[0][0]["ingredient"] is None and read[0][0]["similar"] == []
    # Changing the recipe itself, it doesn't cite itself.
    body["recipe_id"] = blend
    read = _read(await admin.post("/api/ingredient-lines/check", json=body))
    assert read[0][0]["recipe"] is None


async def test_the_source_must_be_one_you_may_add_to(client, broker, adb) -> None:
    await _sign_in(client, broker)
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Not Yours') RETURNING id"))
    response = await client.post(
        "/api/ingredient-lines/check", json={"lines": ["x"], "source_id": str(book)}
    )
    assert response.status_code == 403


async def test_the_check_says_which_lines_saving_refuses(client, broker) -> None:
    await _sign_in(client, broker)
    lines = ["200g rhubarb", "2 eggs", "00 flour"]
    response = await client.post("/api/ingredient-lines/check", json={"lines": lines})
    assert [r["refused"] for r in response.json()["lines"]] == [True, False, False]
