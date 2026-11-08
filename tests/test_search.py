"""Searching for the recipes that use several ingredients at once."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in

E = uuid.uuid4()


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


async def _id(adb, name):
    return await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": name})


async def _search(client, *ids, **params):
    params = {"ingredient": [str(i) for i in ids], **params}
    return (await client.get("/api/search", params=params)).json()


def _titles(found):
    return [r["title"] for r in found["recipes"]]


async def test_a_recipe_must_use_every_ingredient(admin, work, adb, client) -> None:
    await _add(admin, work, "Rhubarb Crumble", "12", ["Rhubarb", "Ginger", "Oats"])
    await _add(admin, work, "Rhubarb Fool", "14", ["Rhubarb", "Cream"])
    await _add(admin, work, "Ginger Biscuits", "30", ["Ginger", "Rhubarb", "Flour"])
    await _add(admin, work, "Gingerbread", "31", ["Ginger"])
    rhubarb, ginger = await _id(adb, "Rhubarb"), await _id(adb, "Ginger")
    found = await _search(client, rhubarb, ginger)
    assert found["ingredients"] == [
        {"id": str(rhubarb), "name": "Rhubarb"},
        {"id": str(ginger), "name": "Ginger"},
    ]
    assert found["missing"] == []
    assert found["total"] == 2
    assert [(r["title"], r["book_title"], r["pages"]) for r in found["recipes"]] == [
        ("Ginger Biscuits", "Pink Cake", ["30"]),
        ("Rhubarb Crumble", "Pink Cake", ["12"]),
    ]


async def test_any_option_on_a_line_counts(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", "1", ["Butter or Coconut Oil", "Egg"])
    found = await _search(client, await _id(adb, "Coconut Oil"), await _id(adb, "Egg"))
    assert _titles(found) == ["Cake"]


async def test_a_recipe_using_one_twice_is_listed_once(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", "1", ["Butter or Margarine", "Margarine"])
    found = await _search(client, await _id(adb, "Margarine"))
    assert (_titles(found), found["total"]) == (["Cake"], 1)


async def test_an_ingredient_finds_the_ones_under_it(admin, work, adb, client) -> None:
    await _add(admin, work, "Rarebit", "1", ["Aged Cheddar", "Bread"])
    await _add(admin, work, "Toastie", "2", ["Cheese", "Bread"])
    await _add(admin, work, "Toast", "3", ["Bread"])
    cheese, cheddar, aged = [await _id(adb, n) for n in ("Cheese", "Cheddar", "Aged Cheddar")]
    assert cheddar is None
    cheddar = await adb.scalar(
        text("INSERT INTO ingredients (name, match_key) VALUES ('Cheddar', 'cheddar') RETURNING id")
    )
    parent = "UPDATE ingredients SET parent_id = :p WHERE id = :i"
    await adb.execute(text(parent), {"p": cheese, "i": cheddar})
    await adb.execute(text(parent), {"p": cheddar, "i": aged})
    assert _titles(await _search(client, cheese, await _id(adb, "Bread"))) == [
        "Rarebit",
        "Toastie",
    ]
    # Not upward: a search for aged cheddar isn't one for any cheese.
    assert _titles(await _search(client, aged)) == ["Rarebit"]


async def test_a_loop_in_the_hierarchy_still_ends(admin, work, adb, client) -> None:
    await _add(admin, work, "Rarebit", "1", ["Cheese", "Cheddar"])
    cheese, cheddar = await _id(adb, "Cheese"), await _id(adb, "Cheddar")
    parent = "UPDATE ingredients SET parent_id = :p WHERE id = :i"
    await adb.execute(text(parent), {"p": cheese, "i": cheddar})
    await adb.execute(text(parent), {"p": cheddar, "i": cheese})
    assert _titles(await _search(client, cheese)) == ["Rarebit"]


async def test_a_missing_ingredient_is_reported_and_the_rest_searched(
    admin, work, adb, client
) -> None:
    await _add(admin, work, "Cake", "1", ["Egg"])
    gone = uuid.uuid4()
    found = await _search(client, gone, await _id(adb, "Egg"))
    assert found["missing"] == [str(gone)]
    assert [i["name"] for i in found["ingredients"]] == ["Egg"]
    assert _titles(found) == ["Cake"]
    nothing = await _search(client, gone)
    assert (nothing["ingredients"], nothing["recipes"], nothing["total"]) == ([], [], 0)


async def test_an_ingredient_asked_twice_counts_once(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", "1", ["Egg"])
    egg = await _id(adb, "Egg")
    found = await _search(client, egg, egg)
    assert [i["name"] for i in found["ingredients"]] == ["Egg"]


async def test_results_come_in_pages(admin, work, adb, client, monkeypatch) -> None:
    monkeypatch.setattr("openlarder.routers.ingredients.PAGE", 2)
    for n in range(5):
        await _add(admin, work, f"Cake {n}", str(n), ["Egg"])
    egg = await _id(adb, "Egg")
    first = await _search(client, egg)
    rest = await _search(client, egg, offset=4)
    assert (_titles(first), first["total"]) == (["Cake 0", "Cake 1"], 5)
    assert _titles(rest) == ["Cake 4"]


async def test_a_search_needs_one_to_ten_ingredients(client) -> None:
    assert (await client.get("/api/search")).status_code == 422
    many = {"ingredient": [str(uuid.uuid4()) for _ in range(11)]}
    assert (await client.get("/api/search", params=many)).status_code == 422
    ten = {"ingredient": [str(uuid.uuid4()) for _ in range(10)]}
    assert (await client.get("/api/search", params=ten)).status_code == 200


async def test_a_page_not_recorded_is_left_off(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", None, ["Egg"])
    found = await _search(client, await _id(adb, "Egg"))
    assert [r["pages"] for r in found["recipes"]] == [[]]


# Within one book


async def _other_book(adb):
    other = await adb.scalar(text("INSERT INTO works (title) VALUES ('Plenty') RETURNING id"))
    edition = uuid.uuid4()
    await adb.execute(
        text("INSERT INTO editions (id, work_id) VALUES (:id, :w)"), {"id": edition, "w": other}
    )
    return other, edition


async def test_a_search_can_stay_in_one_book(admin, work, adb, client) -> None:
    other, edition = await _other_book(adb)
    await _add(admin, work, "Rhubarb Cake", "1", ["Rhubarb", "Egg"])
    response = await admin.post(
        f"/api/books/{other}/recipes",
        json={
            "title": "Rhubarb Salad",
            "editions": [{"edition_id": str(edition), "page": "9"}],
            "ingredients": ["Rhubarb"],
        },
    )
    assert response.status_code == 201
    rhubarb = await _id(adb, "Rhubarb")
    assert _titles(await _search(client, rhubarb)) == ["Rhubarb Cake", "Rhubarb Salad"]
    found = await _search(client, rhubarb, book=str(other))
    assert found["book"] == {"id": str(other), "name": "Plenty"}
    assert (_titles(found), found["total"]) == (["Rhubarb Salad"], 1)
    assert (await _search(client, rhubarb))["book"] is None


async def test_an_unknown_book_is_a_404(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", "1", ["Egg"])
    params = {"ingredient": [str(await _id(adb, "Egg"))], "book": str(uuid.uuid4())}
    assert (await client.get("/api/search", params=params)).status_code == 404


async def test_a_book_lists_the_ingredients_it_uses_most(admin, work, adb, client) -> None:
    other, edition = await _other_book(adb)
    await _add(admin, work, "A", "1", ["Egg", "Butter or Margarine", "Margarine"])
    await _add(admin, work, "B", "2", ["Egg", "Flour"])
    await _add(admin, work, "C", "3", ["Butter"])
    await _add(admin, work, "D", "4", ["Margarine"])
    for title in ("X", "Y", "Z"):
        await admin.post(
            f"/api/books/{other}/recipes",
            json={
                "title": title,
                "editions": [{"edition_id": str(edition)}],
                "ingredients": ["Flour"],
            },
        )
    book = (await client.get(f"/api/books/{work}")).json()
    # Counted in this book only, each recipe once; a tie goes by name.
    assert [(i["name"], i["recipes"]) for i in book["ingredients"]] == [
        ("Butter", 2),
        ("Egg", 2),
        ("Margarine", 2),
        ("Flour", 1),
    ]
    assert book["ingredients"][0]["id"] == str(await _id(adb, "Butter"))


async def test_a_book_shows_its_thirty_most_used(admin, work, client) -> None:
    await _add(admin, work, "A", "1", [f"Spice {n:02}" for n in range(35)])
    book = (await client.get(f"/api/books/{work}")).json()
    assert [i["name"] for i in book["ingredients"]] == [f"Spice {n:02}" for n in range(30)]
