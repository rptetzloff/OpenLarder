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
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    for edition, isbn13, year in ((E1, "9780393541113", 2023), (E2, "9781399611329", 2024)):
        await adb.execute(
            text(
                "INSERT INTO editions (id, source_id, isbn13, published_year)"
                " VALUES (:id, :w, :i, :y)"
            ),
            {"id": edition, "w": work, "i": isbn13, "y": year},
        )
    other = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Other') RETURNING id"))
    other_edition = await adb.scalar(
        text("INSERT INTO editions (source_id) VALUES (:w) RETURNING id"), {"w": other}
    )
    return {"work": work, "other_edition": other_edition}


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET role = 'admin'"))
    return client


def _body(**changes):
    body = {
        "title": "  Rhubarb   Cake ",
        "editions": [{"edition_id": str(E1), "page": " 112 "}, {"edition_id": str(E2)}],
        "ingredients": ["rhubarb", "", "  vanilla   pod ", "caster sugar"],
    }
    return {**body, **changes}


async def _add(client, work, **changes):
    return await client.post(f"/api/sources/{work}/recipes", json=_body(**changes))


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
        ("Cake", [(E1, "1"), (E1, "2")], [], "once"),
        ("Cake", [(E1, "1" * 21)], [], "page"),
        ("Cake", [(E1, None)], ["x" * 151], "method"),
        ("Cake", [(E1, None)], ["200g rhubarb"], "amount"),
        ("Cake", [(E1, None)], ["½ cup milk"], "amount"),
        ("Cake", [(E1, None)], ["rhubarb", "2 cups milk"], "2 cups milk"),
        ("Cake", [(E1, None)], [f"ingredient {i}" for i in range(151)], "150"),
    ],
)
def test_entries_that_break_a_rule_say_which(title, pages, lines, reason) -> None:
    with pytest.raises(recipes.InvalidRecipe, match=reason):
        recipes.clean(title, pages, lines)


def test_each_ingredient_is_kept_once_ignoring_case() -> None:
    entry = recipes.clean("Cake", [(E1, None)], ["butter", "sugar", "Butter", "eggs", "BUTTER"])
    assert entry.lines == ["butter", "sugar", "eggs"]


def test_a_long_choice_of_ingredients_fits() -> None:
    line = "x" * 150
    assert recipes.clean("Cake", [(E1, None)], [line]).lines == [line]


@pytest.mark.parametrize(
    "amount",
    [
        "200g rhubarb",
        "200 g rhubarb",
        "2 cups milk",
        "1 tsp vanilla",
        "1-2 tsp salt",
        "1/2 lb butter",
        "1.5 kg flour",
        "2 to 3 cups stock",
        "4oz chocolate",
        "1 can tomatoes",
        "2 Cloves Garlic",
    ],
)
def test_a_number_with_a_unit_is_an_amount(amount) -> None:
    with pytest.raises(recipes.InvalidRecipe, match="amount"):
        recipes.clean("Cake", [(E1, None)], [amount])


@pytest.mark.parametrize(
    "name",
    [
        "00 flour",
        "2% milk",
        "160 bloom gelatin",
        "7-minute frosting",
        "80-proof vodka",
        "5-spice powder",
        "70% dark chocolate",
        "15-bean soup mix",
        "63.5C eggs",
        "1-2-3 cookie dough",
        "cloves",
        "garlic",
    ],
)
def test_a_number_without_a_unit_can_be_part_of_a_name(name) -> None:
    assert recipes.clean("Cake", [(E1, None)], [name]).lines == [name]


# Adding, reading, changing, removing


async def test_adding_a_recipe_stores_pages_and_lines_in_order(admin, book, adb) -> None:
    response = await _add(admin, book["work"])
    assert response.status_code == 201
    recipe = (await admin.get(f"/api/recipes/{response.json()['id']}")).json()

    assert recipe["title"] == "Rhubarb Cake"
    assert recipe["source"]["title"] == "Pink Cake"
    assert recipe["ingredients"] == ["rhubarb", "vanilla pod", "caster sugar"]
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
            text("SELECT count(*) FROM recipe_locations WHERE recipe_id = :r"), {"r": recipe_id}
        )
        == 1
    )


async def test_the_book_page_lists_recipes_with_their_pages(admin, client, book) -> None:
    await _add(
        admin, book["work"], title="banana bread", editions=[{"edition_id": str(E1), "page": "5"}]
    )
    await _add(admin, book["work"])
    listed = (await client.get(f"/api/sources/{book['work']}")).json()["recipes"]
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


async def test_a_chapter_is_kept_tidied_and_changed(admin, client, book) -> None:
    added = await _add(admin, book["work"], chapter="  Yeast   Breads ")
    recipe_id = added.json()["id"]
    assert (await client.get(f"/api/recipes/{recipe_id}")).json()["chapter"] == "Yeast Breads"
    listed = (await client.get(f"/api/sources/{book['work']}")).json()["recipes"]
    assert [r["chapter"] for r in listed] == ["Yeast Breads"]
    # Blank takes it off.
    await admin.put(f"/api/recipes/{recipe_id}", json=_body(chapter=" "))
    assert (await client.get(f"/api/recipes/{recipe_id}")).json()["chapter"] is None
    too_long = await admin.put(f"/api/recipes/{recipe_id}", json=_body(chapter="x" * 101))
    assert too_long.status_code == 422


async def test_removing_a_recipe_removes_its_pages_and_lines(admin, book, adb) -> None:
    recipe_id = (await _add(admin, book["work"])).json()["id"]
    assert (await admin.delete(f"/api/recipes/{recipe_id}")).status_code == 204
    assert (await admin.get(f"/api/recipes/{recipe_id}")).status_code == 404
    for table in ("recipes", "recipe_locations", "recipe_ingredients"):
        assert await adb.scalar(text(f"SELECT count(*) FROM {table}")) == 0


async def test_an_amount_is_refused_and_nothing_is_stored(admin, book, adb) -> None:
    response = await _add(admin, book["work"], ingredients=["rhubarb", "200g caster sugar"])
    assert response.status_code == 422
    assert "Leave out the amount" in response.json()["detail"]
    assert await adb.scalar(text("SELECT count(*) FROM recipes")) == 0


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
    await adb.execute(text("UPDATE users SET role = 'user'"))
    assert (await admin.put(f"/api/recipes/{recipe_id}", json=_body())).status_code == 403
    assert (await admin.delete(f"/api/recipes/{recipe_id}")).status_code == 403
    assert await adb.scalar(text("SELECT count(*) FROM recipes")) == 1


async def test_another_sites_page_cannot_write(admin, book) -> None:
    origin = {"Origin": "https://auth.openlarder.com"}
    response = await admin.post(
        f"/api/sources/{book['work']}/recipes", json=_body(), headers=origin
    )
    assert response.status_code == 403


async def test_reading_is_public(admin, client, book) -> None:
    recipe_id = (await _add(admin, book["work"])).json()["id"]
    await admin.post("/api/auth/logout")
    assert (await client.get(f"/api/recipes/{recipe_id}")).status_code == 200


def test_migration_0011_refuses_to_drop_an_amount(engine, alembic_config) -> None:
    from alembic import command

    engine.dispose()
    command.downgrade(alembic_config, "0010")
    try:
        with engine.begin() as conn:
            work = conn.execute(
                text("INSERT INTO works (title) VALUES ('Amounts') RETURNING id")
            ).scalar_one()
            recipe = conn.execute(
                text("INSERT INTO recipes (work_id, title) VALUES (:w, 'Cake') RETURNING id"),
                {"w": work},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO recipe_ingredients (recipe_id, position, original_text, quantity)"
                    " VALUES (:r, 1, 'rhubarb', '200g')"
                ),
                {"r": recipe},
            )
        with pytest.raises(RuntimeError, match="amount"):
            command.upgrade(alembic_config, "head")
    finally:
        # Still at 0010 when 0011 refused: the table is works there.
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM works WHERE title = 'Amounts'"))
        command.upgrade(alembic_config, "head")


# Entering a whole book


async def test_every_recipes_lines_come_in_order(admin, client, book) -> None:
    first = (await _add(admin, book["work"])).json()["id"]
    second = (await _add(admin, book["work"], title="Bare", ingredients=[])).json()["id"]
    response = await client.get(f"/api/sources/{book['work']}/recipe-lines")
    assert {r["id"]: r["lines"] for r in response.json()} == {
        first: ["rhubarb", "vanilla pod", "caster sugar"],
        second: [],
    }


async def test_lines_for_a_source_that_does_not_exist(client) -> None:
    response = await client.get(f"/api/sources/{uuid.uuid4()}/recipe-lines")
    assert response.status_code == 404
