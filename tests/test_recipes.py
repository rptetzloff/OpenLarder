"""Recipe entries: what can be typed, and adding, changing and removing them."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in
from openlarder import recipes

E1, E2 = uuid.uuid4(), uuid.uuid4()


@pytest.fixture
async def book(adb):
    """A book with two editions, and a second book with one."""
    work = await adb.scalar(text("INSERT INTO works (title) VALUES ('Pink Cake') RETURNING id"))
    for edition, isbn13, year in ((E1, "9780393541113", 2023), (E2, "9781399611329", 2024)):
        await adb.execute(
            text(
                "INSERT INTO editions (id, work_id, isbn13, published_year)"
                " VALUES (:id, :w, :i, :y)"
            ),
            {"id": edition, "w": work, "i": isbn13, "y": year},
        )
    other = await adb.scalar(text("INSERT INTO works (title) VALUES ('Other') RETURNING id"))
    other_edition = await adb.scalar(
        text("INSERT INTO editions (work_id) VALUES (:w) RETURNING id"), {"w": other}
    )
    return {"work": work, "other_edition": other_edition}


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET is_admin = true"))
    return client


def _body(**changes):
    body = {
        "title": "  Rhubarb   Cake ",
        "editions": [{"edition_id": str(E1), "page": " 112 "}, {"edition_id": str(E2)}],
        "ingredients": ["200g rhubarb", "", "  1 tsp   vanilla ", "100g sugar"],
    }
    return {**body, **changes}


async def _add(client, work, **changes):
    return await client.post(f"/api/books/{work}/recipes", json=_body(**changes))


# What can be typed


def test_entries_are_tidied() -> None:
    entry = recipes.clean(" Rhubarb\n Cake ", [(E1, " 112 "), (E2, "  ")], ["a ", "", " b  c"])
    assert entry.title == "Rhubarb Cake"
    assert entry.pages == {E1: "112", E2: None}
    assert entry.lines == ["a", "b c"]


@pytest.mark.parametrize(
    "title, pages, lines, reason",
    [
        ("  ", [(E1, None)], [], "title"),
        ("x" * 201, [(E1, None)], [], "200"),
        ("Cake", [], [], "edition"),
        ("Cake", [(E1, "1"), (E1, "2")], [], "once"),
        ("Cake", [(E1, "1" * 21)], [], "page"),
        ("Cake", [(E1, None)], ["x" * 301], "method"),
        ("Cake", [(E1, None)], ["x"] * 151, "150"),
    ],
)
def test_entries_that_break_a_rule_say_which(title, pages, lines, reason) -> None:
    with pytest.raises(recipes.InvalidRecipe, match=reason):
        recipes.clean(title, pages, lines)


# Adding, reading, changing, removing


async def test_adding_a_recipe_stores_pages_and_lines_in_order(admin, book, adb) -> None:
    response = await _add(admin, book["work"])
    assert response.status_code == 201
    recipe = (await admin.get(f"/api/recipes/{response.json()['id']}")).json()

    assert recipe["title"] == "Rhubarb Cake"
    assert recipe["book"]["title"] == "Pink Cake"
    assert recipe["ingredients"] == ["200g rhubarb", "1 tsp vanilla", "100g sugar"]
    # Newest edition first; a blank page means in it, page not recorded.
    assert [(p["published_year"], p["page"]) for p in recipe["pages"]] == [
        (2024, None),
        (2023, "112"),
    ]


async def test_an_edition_left_out_is_one_the_recipe_is_not_in(admin, book, adb) -> None:
    response = await _add(admin, book["work"], editions=[{"edition_id": str(E1), "page": "9"}])
    recipe_id = response.json()["id"]
    assert (
        await adb.scalar(
            text("SELECT count(*) FROM recipe_pages WHERE recipe_id = :r"), {"r": recipe_id}
        )
        == 1
    )


async def test_the_book_page_lists_recipes_with_their_pages(admin, client, book) -> None:
    await _add(
        admin, book["work"], title="banana bread", editions=[{"edition_id": str(E1), "page": "5"}]
    )
    await _add(admin, book["work"])
    listed = (await client.get(f"/api/books/{book['work']}")).json()["recipes"]
    assert [(r["title"], r["pages"]) for r in listed] == [
        ("banana bread", ["5"]),
        ("Rhubarb Cake", [None, "112"]),
    ]


async def test_a_page_in_another_books_edition_is_refused(admin, book, adb) -> None:
    response = await _add(
        admin, book["work"], editions=[{"edition_id": str(book["other_edition"])}]
    )
    assert response.status_code == 422
    assert await adb.scalar(text("SELECT count(*) FROM recipes")) == 0


async def test_changing_a_recipe_rewrites_its_pages_and_lines(admin, book, adb) -> None:
    recipe_id = (await _add(admin, book["work"])).json()["id"]
    response = await admin.put(
        f"/api/recipes/{recipe_id}",
        json=_body(
            title="Rhubarb Crumble Cake",
            editions=[{"edition_id": str(E2), "page": "120"}],
            ingredients=["rhubarb"],
        ),
    )
    assert response.status_code == 200
    changed = response.json()
    assert changed["title"] == "Rhubarb Crumble Cake"
    assert [(p["edition_id"], p["page"]) for p in changed["pages"]] == [(str(E2), "120")]
    assert changed["ingredients"] == ["rhubarb"]
    assert await adb.scalar(text("SELECT count(*) FROM recipe_ingredients")) == 1


async def test_removing_a_recipe_removes_its_pages_and_lines(admin, book, adb) -> None:
    recipe_id = (await _add(admin, book["work"])).json()["id"]
    assert (await admin.delete(f"/api/recipes/{recipe_id}")).status_code == 204
    assert (await admin.get(f"/api/recipes/{recipe_id}")).status_code == 404
    for table in ("recipes", "recipe_pages", "recipe_ingredients"):
        assert await adb.scalar(text(f"SELECT count(*) FROM {table}")) == 0


async def test_an_invalid_entry_says_why(admin, book) -> None:
    response = await _add(admin, book["work"], title=" ")
    assert response.status_code == 422
    assert "title" in response.json()["detail"]


async def test_a_recipe_for_a_book_that_does_not_exist(admin) -> None:
    response = await _add(admin, uuid.uuid4())
    assert response.status_code == 404


# Who may


async def test_only_an_admin_can_write(client, broker, book, adb) -> None:
    assert (await _add(client, book["work"])).status_code == 401
    await _sign_in(client, broker)
    assert (await _add(client, book["work"])).status_code == 403
    assert await adb.scalar(text("SELECT count(*) FROM recipes")) == 0


async def test_a_non_admin_cannot_change_or_remove(admin, client, broker, book, adb) -> None:
    recipe_id = (await _add(admin, book["work"])).json()["id"]
    await adb.execute(text("UPDATE users SET is_admin = false"))
    assert (await admin.put(f"/api/recipes/{recipe_id}", json=_body())).status_code == 403
    assert (await admin.delete(f"/api/recipes/{recipe_id}")).status_code == 403
    assert await adb.scalar(text("SELECT count(*) FROM recipes")) == 1


async def test_another_sites_page_cannot_write(admin, book) -> None:
    origin = {"Origin": "https://auth.openlarder.com"}
    response = await admin.post(f"/api/books/{book['work']}/recipes", json=_body(), headers=origin)
    assert response.status_code == 403


async def test_reading_is_public(admin, client, book) -> None:
    recipe_id = (await _add(admin, book["work"])).json()["id"]
    await admin.post("/api/auth/logout")
    assert (await client.get(f"/api/recipes/{recipe_id}")).status_code == 200
