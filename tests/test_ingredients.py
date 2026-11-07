"""Canonical ingredients: the matching key, matching lines, and reading them back."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in
from openlarder.ingredients import match_key

E = uuid.uuid4()


# The key


@pytest.mark.parametrize(
    "a, b",
    [
        ("Cinnamon Sticks", "cinnamon stick"),
        ("Long-Grain Rice", "Long Grain Rice"),
        ("Berries", "berry"),
        ("Tomatoes", "Tomato"),
        ("Black Peppercorns", "Black Peppercorn"),
        ("Salt & Pepper", "salt and pepper"),
        ("St. Germain", "St Germain"),
        ("Peas", "pea"),
    ],
)
def test_variants_share_a_key(a, b) -> None:
    assert match_key(a) == match_key(b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("Rosé", "Rose"),  # the wine and the flower
        ("Fresh Ginger", "Ginger"),
        ("Grass", "Gras"),
        ("Pineapple (Can)", "Pineapple"),
    ],
)
def test_different_ingredients_keep_different_keys(a, b) -> None:
    assert match_key(a) != match_key(b)


def test_a_name_of_only_punctuation_has_no_key() -> None:
    assert match_key("—") == ""


@pytest.mark.parametrize(
    "name, key",
    [("Swiss Chard", "swiss chard"), ("Sea Bass", "sea bass"), ("Blackberries", "blackberri")],
)
def test_the_key_spelled_out(name, key) -> None:
    assert match_key(name) == key


# Matching, through the recipe routes


@pytest.fixture
async def work(adb):
    work = await adb.scalar(text("INSERT INTO works (title) VALUES ('Pink Cake') RETURNING id"))
    await adb.execute(
        text("INSERT INTO editions (id, work_id) VALUES (:id, :w)"), {"id": E, "w": work}
    )
    return work


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET is_admin = true"))
    return client


async def _add(client, work, title, page, ingredients):
    response = await client.post(
        f"/api/books/{work}/recipes",
        json={
            "title": title,
            "editions": [{"edition_id": str(E), "page": page}],
            "ingredients": ingredients,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _ingredients(adb):
    return (await adb.scalars(text("SELECT name FROM ingredients ORDER BY name"))).all()


async def test_each_option_is_matched_to_an_ingredient(admin, work, adb) -> None:
    await _add(admin, work, "Cake", "1", ["Grapeseed Oil or Olive Oil", "Egg"])
    assert await _ingredients(adb) == ["Egg", "Grapeseed Oil", "Olive Oil"]
    unmatched = await adb.scalar(
        text("SELECT count(*) FROM ingredient_options WHERE ingredient_id IS NULL")
    )
    assert unmatched == 0


async def test_variants_match_one_ingredient_named_as_the_book_mostly_does(admin, work, adb):
    await _add(admin, work, "A", "1", ["Cinnamon Sticks"])
    await _add(admin, work, "B", "2", ["Cinnamon Stick"])
    await _add(admin, work, "C", "3", ["cinnamon stick"])
    assert await _ingredients(adb) == ["Cinnamon Sticks"]
    distinct = await adb.scalar(
        text("SELECT count(DISTINCT ingredient_id) FROM ingredient_options")
    )
    assert distinct == 1


async def test_a_new_ingredient_takes_the_most_used_spelling(admin, work, adb) -> None:
    """Matched together, as an import or the Admin catch-up does a whole book."""
    for title, page, line in [("A", "1", "Sea Scallops"), ("B", "2", "Sea Scallop")]:
        await _add(admin, work, title, page, [line])
    await adb.execute(text("UPDATE ingredient_options SET ingredient_id = NULL"))
    await adb.execute(text("DELETE FROM ingredients"))
    await _add(admin, work, "C", "3", ["Sea Scallops"])
    assert await _ingredients(adb) == ["Sea Scallops"]


async def test_references_and_components_are_not_ingredients(admin, work, adb) -> None:
    await _add(admin, work, "Basic Cauli-Rice", "269", ["Cauliflower"])
    await _add(
        admin, work, "Curry", "101", ["Basic Cauli-Rice (p. 269)", "Filling (p. 999)", "Chicken"]
    )
    assert await _ingredients(adb) == ["Cauliflower", "Chicken"]


async def test_a_name_with_no_letters_is_left_unmatched(admin, work, adb) -> None:
    await _add(admin, work, "Cake", "1", ["—", "Egg"])
    assert await _ingredients(adb) == ["Egg"]


async def test_an_ingredient_is_shared_across_books(admin, work, adb) -> None:
    other = await adb.scalar(text("INSERT INTO works (title) VALUES ('Other') RETURNING id"))
    edition = uuid.uuid4()
    await adb.execute(
        text("INSERT INTO editions (id, work_id) VALUES (:id, :w)"), {"id": edition, "w": other}
    )
    await _add(admin, work, "Cake", "1", ["Butter"])
    response = await admin.post(
        f"/api/books/{other}/recipes",
        json={
            "title": "Toast",
            "editions": [{"edition_id": str(edition)}],
            "ingredients": ["butter"],
        },
    )
    assert response.status_code == 201
    assert await _ingredients(adb) == ["Butter"]


async def test_the_recipe_page_links_each_ingredient(admin, work, adb) -> None:
    recipe = await _add(admin, work, "Cake", "1", ["Egg"])
    egg = await adb.scalar(text("SELECT id FROM ingredients"))
    option = (await admin.get(f"/api/recipes/{recipe}")).json()["lines"][0]["options"][0]
    assert option["ingredient"] == {"id": str(egg), "name": "Egg"}


async def test_an_edit_keeps_the_same_ingredient(admin, work, adb) -> None:
    recipe = await _add(admin, work, "Cake", "1", ["Eggs"])
    egg = await adb.scalar(text("SELECT id FROM ingredients"))
    response = await admin.put(
        f"/api/recipes/{recipe}",
        json={
            "title": "Cake",
            "editions": [{"edition_id": str(E), "page": "1"}],
            "ingredients": ["Egg"],
        },
    )
    assert response.json()["lines"][0]["options"][0]["ingredient"]["id"] == str(egg)
    assert await _ingredients(adb) == ["Eggs"]


# Reading


async def test_the_list_puts_the_most_used_first(admin, work, client) -> None:
    await _add(admin, work, "A", "1", ["Egg", "Butter"])
    await _add(admin, work, "B", "2", ["Egg"])
    listed = (await client.get("/api/ingredients")).json()
    assert [(i["name"], i["recipes"]) for i in listed["ingredients"]] == [("Egg", 2), ("Butter", 1)]
    assert listed["total"] == 2


async def test_the_list_narrows_by_name(admin, work, client) -> None:
    await _add(admin, work, "A", "1", ["Olive Oil", "Grapeseed Oil", "Egg", "100% Rye Flour"])
    names = lambda r: [i["name"] for i in r.json()["ingredients"]]  # noqa: E731
    assert sorted(names(await client.get("/api/ingredients", params={"q": " oil "}))) == [
        "Grapeseed Oil",
        "Olive Oil",
    ]
    # Wildcards are typed characters, not patterns.
    assert names(await client.get("/api/ingredients", params={"q": "%"})) == ["100% Rye Flour"]
    assert names(await client.get("/api/ingredients", params={"q": "_"})) == []


async def test_an_ingredient_lists_its_recipes_with_book_and_page(admin, work, client) -> None:
    cake = await _add(admin, work, "Rhubarb Cake", "112", ["Rhubarb", "Sugar"])
    await _add(admin, work, "Apple Pie", "90", ["Sugar"])
    sugar = next(
        i
        for i in (await client.get("/api/ingredients")).json()["ingredients"]
        if i["name"] == "Sugar"
    )
    shown = (await client.get(f"/api/ingredients/{sugar['id']}")).json()
    assert shown["name"] == "Sugar"
    assert shown["total"] == 2
    assert [(r["title"], r["book_title"], r["pages"]) for r in shown["recipes"]] == [
        ("Apple Pie", "Pink Cake", ["90"]),
        ("Rhubarb Cake", "Pink Cake", ["112"]),
    ]
    assert cake in [r["id"] for r in shown["recipes"]]


async def test_a_recipe_using_an_ingredient_twice_is_listed_once(admin, work, client) -> None:
    await _add(admin, work, "Cake", "1", ["Butter or Margarine", "Margarine"])
    listed = (await client.get("/api/ingredients", params={"q": "margarine"})).json()
    assert listed["ingredients"][0]["recipes"] == 1


async def test_an_unknown_ingredient_is_a_404(client) -> None:
    assert (await client.get(f"/api/ingredients/{uuid.uuid4()}")).status_code == 404
