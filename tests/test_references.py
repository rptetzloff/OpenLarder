"""Ingredient lines read into options, and page references linked to recipes.

The lines are the household index's own shapes: "Basic Cauli-Rice (p. 269),
Noodles, or Potato", "Tomato Sauce (p. 114)" printed inside the ravioli on
page 114, "Basic Dry Pancake Mix (p. 150)" for a mix that is on page 149.
"""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in
from openlarder import lines
from openlarder.lines import Option

E = uuid.uuid4()


# Reading a line


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Garlic", [Option("Garlic", None)]),
        ("Grapeseed Oil or Olive Oil", [Option("Grapeseed Oil", None), Option("Olive Oil", None)]),
        (
            "Dry Sherry, Hard Cider, or Dry White Wine",
            [
                Option("Dry Sherry", None),
                Option("Hard Cider", None),
                Option("Dry White Wine", None),
            ],
        ),
        (
            "Basic Cauli-Rice (p. 269), Noodles, or Potato",
            [Option("Basic Cauli-Rice", "269"), Option("Noodles", None), Option("Potato", None)],
        ),
        (
            "Mashed Potato (p. 266) or Basic Cauli-Rice (p. 269)",
            [Option("Mashed Potato", "266"), Option("Basic Cauli-Rice", "269")],
        ),
        # Commas in a name, with no ", or" list: one option.
        (
            "Lemon, Orange, and Grapefruit Marmalade",
            [Option("Lemon, Orange, and Grapefruit Marmalade", None)],
        ),
        ("Marmalade, Lemon or Orange", [Option("Marmalade, Lemon", None), Option("Orange", None)]),
        # Nothing inside brackets is split.
        ("Anise Liqueur (Raki or Pernod)", [Option("Anise Liqueur (Raki or Pernod)", None)]),
        # Page reference shapes, including the index's unclosed "(p. 605".
        ("Gravy (p. 605", [Option("Gravy", "605")]),
        ("Stock (pp. 12-13)", [Option("Stock", "12")]),
        ("Royal Icing (pg 146)", [Option("Royal Icing", "146")]),
        ("Pastry (P. xii)", [Option("Pastry", "xii")]),
        # A reference mid-line isn't the option's page.
        (
            "Bone Broth (p. 110) with Lemon Juice",
            [Option("Bone Broth (p. 110) with Lemon Juice", None)],
        ),
        # Words that merely contain "or" don't split.
        ("Orange Liqueur", [Option("Orange Liqueur", None)]),
        ("Cornflour", [Option("Cornflour", None)]),
    ],
)
def test_a_line_is_read_into_its_options(line, expected) -> None:
    assert lines.options(line) == expected


@pytest.mark.parametrize("line", ["or Olive Oil", "Olive Oil or", "Butter, or"])
def test_a_dangling_or_leaves_the_line_whole(line) -> None:
    assert [o.name for o in lines.options(line)] == [line.strip()]


@pytest.mark.parametrize(
    "line",
    [
        # Each would leave an option with no name, which the database refuses.
        "(p. 42)",
        "Salt, , or Pepper",
        "Olive Oil or (p. 12)",
    ],
)
def test_an_option_always_has_a_name(line) -> None:
    assert all(o.name for o in lines.options(line))
    assert lines.options("(p. 42)") == [Option("(p. 42)", None)]


# Resolving a reference, on its own


def _book(*recipes):
    book = [lines.BookRecipe(uuid.uuid4(), title, frozenset(pages)) for title, pages in recipes]
    by_title = {}
    for r in book:
        by_title.setdefault(r.title.casefold(), []).append(r)
    return book, by_title


def test_a_reference_by_name_and_page() -> None:
    book, by_title = _book(("Basic Cauli-Rice", {"269"}), ("Pork Chile Verde", {"229"}))
    resolved = lines.resolve(book[1].id, Option("basic cauli-rice", "269"), book, by_title)
    assert resolved == lines.Resolved(book[0].id)


def test_a_reference_to_the_wrong_page_links_by_name_and_is_flagged() -> None:
    book, by_title = _book(("Basic Dry Pancake Mix", {"149"}), ("Pancakes", {"151"}))
    resolved = lines.resolve(book[1].id, Option("Basic Dry Pancake Mix", "150"), book, by_title)
    assert resolved.recipe_id == book[0].id
    assert resolved.flag[0].value == "reference_page"
    assert resolved.flag[1] == "Basic Dry Pancake Mix (p. 150) is on p. 149"


def test_a_component_links_to_the_recipe_printed_around_it() -> None:
    book, by_title = _book(("Three-Cheese Ravioli", {"114"}), ("Lasagna", {"120"}))
    resolved = lines.resolve(book[1].id, Option("Tomato Sauce", "114"), book, by_title)
    assert resolved == lines.Resolved(book[0].id)


def test_a_component_of_the_recipe_itself_stays_unlinked() -> None:
    book, by_title = _book(("Three-Cheese Ravioli", {"114"}))
    assert lines.resolve(book[0].id, Option("Tomato Sauce", "114"), book, by_title) == (
        lines.Resolved(None)
    )


def test_a_page_with_several_recipes_and_no_name_to_go_on_stays_unlinked() -> None:
    book, by_title = _book(("Mojo", {"270"}), ("Salsa", {"270"}), ("Tacos", {"300"}))
    assert lines.resolve(book[2].id, Option("Sauce", "270"), book, by_title) == (
        lines.Resolved(None)
    )


def test_the_citing_recipe_sharing_the_page_with_no_name_match_stays_unlinked() -> None:
    book, by_title = _book(("Ravioli", {"114"}), ("Pasta Dough", {"114"}))
    assert lines.resolve(book[0].id, Option("Tomato Sauce", "114"), book, by_title) == (
        lines.Resolved(None)
    )


def test_on_a_shared_page_the_name_picks_the_recipe() -> None:
    book, by_title = _book(
        ("Red Meat or Pork Stock", {"475"}),
        ("Chicken, Turkey, Duck, or Goose Stock", {"475"}),
        ("Coddle", {"489"}),
    )
    resolved = lines.resolve(book[2].id, Option("Chicken Stock", "475"), book, by_title)
    assert resolved == lines.Resolved(book[1].id)


def test_on_a_shared_page_words_they_all_share_decide_nothing() -> None:
    book, by_title = _book(("Beef Stock", {"475"}), ("Pork Stock", {"475"}), ("Soup", {"9"}))
    assert lines.resolve(book[2].id, Option("Stock", "475"), book, by_title) == (
        lines.Resolved(None)
    )


def test_small_words_are_not_a_match() -> None:
    book, by_title = _book(("Dressing for Salad", {"80"}), ("Glaze", {"80"}), ("Ham", {"9"}))
    assert lines.resolve(book[2].id, Option("Sauce for Ham", "80"), book, by_title) == (
        lines.Resolved(None)
    )


def test_on_a_shared_page_a_tie_stays_unlinked() -> None:
    book, by_title = _book(("Garlic Sausage", {"505"}), ("Garlic Salt", {"505"}), ("Stew", {"9"}))
    assert lines.resolve(book[2].id, Option("Garlic Mix", "505"), book, by_title) == (
        lines.Resolved(None)
    )


def test_a_page_shared_with_the_citing_recipe_is_decided_by_name() -> None:
    book, by_title = _book(
        ("Fresh Ricotta in 5 Minutes or Less", {"154"}), ("Warm Ricotta Toast", {"154"})
    )
    resolved = lines.resolve(book[1].id, Option("Fresh Ricotta", "154"), book, by_title)
    assert resolved == lines.Resolved(book[0].id)


def test_a_page_with_no_recipe_is_flagged() -> None:
    book, by_title = _book(("Tacos", {"300"}))
    resolved = lines.resolve(book[0].id, Option("Slather", "139"), book, by_title)
    assert resolved.recipe_id is None
    assert resolved.flag[0].value == "unknown_reference"
    assert resolved.flag[1] == "Slather: no recipe on p. 139"


def test_a_recipe_never_links_to_itself_by_name() -> None:
    book, by_title = _book(("Biscuit Blend", {"14"}))
    resolved = lines.resolve(book[0].id, Option("Biscuit Blend", "14"), book, by_title)
    assert resolved.recipe_id is None


def test_an_option_without_a_page_is_not_a_reference() -> None:
    book, by_title = _book(("Biscuit Blend", {"14"}))
    assert lines.resolve(uuid.uuid4(), Option("Biscuit Blend", None), book, by_title) == (
        lines.Resolved(None)
    )


# Stored, through the recipe routes


@pytest.fixture
async def work(adb):
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Healthy') RETURNING id"))
    await adb.execute(
        text("INSERT INTO editions (id, source_id) VALUES (:id, :w)"), {"id": E, "w": work}
    )
    return work


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET role = 'admin'"))
    return client


async def _add(client, work, title, page, ingredients):
    response = await client.post(
        f"/api/sources/{work}/recipes",
        json={
            "title": title,
            "editions": [{"edition_id": str(E), "page": page}],
            "ingredients": ingredients,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _flags(adb):
    rows = await adb.execute(text("SELECT kind, detail FROM recipe_flags ORDER BY kind, detail"))
    return [tuple(r) for r in rows]


async def test_a_reference_links_once_its_recipe_is_added(admin, work, adb) -> None:
    curry = await _add(admin, work, "Curry", "101", ["Chicken", "Basic Cauli-Rice (p. 269)"])
    assert await _flags(adb) == [("unknown_reference", "Basic Cauli-Rice: no recipe on p. 269")]
    rice = await _add(admin, work, "Basic Cauli-Rice", "269", ["Cauliflower"])

    shown = (await admin.get(f"/api/recipes/{curry}")).json()
    assert shown["lines"][1] == {
        "text": "Basic Cauli-Rice (p. 269)",
        "options": [
            {
                "name": "Basic Cauli-Rice",
                "page": "269",
                "recipe": {"id": rice, "title": "Basic Cauli-Rice"},
                "ingredient": None,
            }
        ],
    }
    (chicken,) = shown["lines"][0]["options"]
    assert (chicken["name"], chicken["recipe"]) == ("Chicken", None)
    assert chicken["ingredient"]["name"] == "Chicken"
    # The flag no longer applies, so it went.
    assert await _flags(adb) == []
    used = (await admin.get(f"/api/recipes/{rice}")).json()["used_in"]
    assert used == [{"id": curry, "title": "Curry", "page": "101"}]


async def test_options_are_stored_in_order(admin, work, adb) -> None:
    await _add(admin, work, "Stroganoff", "221", ["Basic Cauli-Rice (p. 269), Noodles, or Potato"])
    names = (await adb.scalars(text("SELECT name FROM ingredient_options ORDER BY rank"))).all()
    assert names == ["Basic Cauli-Rice", "Noodles", "Potato"]


async def test_editing_a_line_relinks_it(admin, work, adb) -> None:
    rice = await _add(admin, work, "Basic Cauli-Rice", "269", ["Cauliflower"])
    curry = await _add(admin, work, "Curry", "101", ["Cauli Rice (p. 260)"])
    assert await _flags(adb) == [("unknown_reference", "Cauli Rice: no recipe on p. 260")]
    response = await admin.put(
        f"/api/recipes/{curry}",
        json={
            "title": "Curry",
            "editions": [{"edition_id": str(E), "page": "101"}],
            "ingredients": ["Basic Cauli-Rice (p. 269)"],
        },
    )
    assert response.status_code == 200
    assert response.json()["lines"][0]["options"][0]["recipe"]["id"] == rice
    assert await _flags(adb) == []


async def test_a_recipe_others_use_can_still_be_removed(admin, work, adb) -> None:
    rice = await _add(admin, work, "Basic Cauli-Rice", "269", ["Cauliflower"])
    curry = await _add(admin, work, "Curry", "101", ["Basic Cauli-Rice (p. 269)"])
    assert (await admin.delete(f"/api/recipes/{rice}")).status_code == 204
    shown = (await admin.get(f"/api/recipes/{curry}")).json()
    assert shown["lines"][0]["options"][0]["recipe"] is None
    assert await _flags(adb) == [("unknown_reference", "Basic Cauli-Rice: no recipe on p. 269")]


async def test_a_dismissed_reference_flag_is_not_raised_again(admin, work, adb) -> None:
    await _add(admin, work, "Curry", "101", ["Slather (p. 139)"])
    await adb.execute(
        text("UPDATE recipe_flags SET resolution = 'dismissed', note = 'ok', resolved_at = now()")
    )
    await _add(admin, work, "Tacos", "300", ["Tortilla"])
    assert await adb.scalar(text("SELECT count(*) FROM recipe_flags")) == 1


async def test_an_open_flag_that_still_applies_is_kept_as_it_is(admin, work, adb) -> None:
    await _add(admin, work, "Curry", "101", ["Slather (p. 139)"])
    first = await adb.scalar(text("SELECT id FROM recipe_flags"))
    await _add(admin, work, "Tacos", "300", ["Tortilla"])
    assert (await adb.scalars(text("SELECT id FROM recipe_flags"))).all() == [first]


async def test_a_dealt_with_flag_stays_when_its_reference_is_fixed(admin, work, adb) -> None:
    """Its history is kept: only open flags that no longer apply are removed."""
    await _add(admin, work, "Curry", "101", ["Slather (p. 139)"])
    await adb.execute(text("UPDATE recipe_flags SET resolution = 'fixed', resolved_at = now()"))
    await _add(admin, work, "Slather", "139", ["Chile"])
    assert await adb.scalar(text("SELECT count(*) FROM recipe_flags")) == 1


async def test_a_wrong_page_is_linked_and_flagged(admin, work, adb) -> None:
    mix = await _add(admin, work, "Basic Dry Pancake Mix", "149", ["Flour"])
    pancakes = await _add(admin, work, "Pancakes", "151", ["Basic Dry Pancake Mix (p. 150)"])
    shown = (await admin.get(f"/api/recipes/{pancakes}")).json()
    assert shown["lines"][0]["options"][0]["recipe"]["id"] == mix
    assert await _flags(adb) == [("reference_page", "Basic Dry Pancake Mix (p. 150) is on p. 149")]


async def test_relinking_leaves_a_matched_option_alone(admin, work, adb) -> None:
    """An option already right keeps what was hung off it, like a corrected match."""
    await _add(admin, work, "Curry", "101", ["Garlic"])
    ingredient = await adb.scalar(
        text("INSERT INTO ingredients (name, match_key) VALUES ('Ail', 'ail') RETURNING id")
    )
    await adb.execute(text("UPDATE ingredient_options SET ingredient_id = :i"), {"i": ingredient})
    await _add(admin, work, "Tacos", "300", ["Tortilla"])
    matched = await adb.scalar(
        text("SELECT ingredient_id FROM ingredient_options WHERE name = 'Garlic'")
    )
    assert matched == ingredient


async def test_an_import_links_a_reference_to_a_later_batch(admin, work, adb) -> None:
    def item(row, title, page, ingredients):
        return {
            "row": row,
            "source_id": str(work),
            "isbn13": None,
            "title": title,
            "page": page,
            "ingredients": ingredients,
        }

    await admin.post(
        "/api/import/recipes",
        json={"items": [item(2, "Curry", "101", ["Basic Cauli-Rice (p. 269)"])]},
    )
    await admin.post(
        "/api/import/recipes", json={"items": [item(3, "Basic Cauli-Rice", "269", ["Cauliflower"])]}
    )
    linked = await adb.scalar(
        text("SELECT r.title FROM ingredient_options o JOIN recipes r ON r.id = o.sub_recipe_id")
    )
    assert linked == "Basic Cauli-Rice"
    assert await _flags(adb) == []


async def test_an_admin_can_link_a_books_references_again(admin, work, adb) -> None:
    await _add(admin, work, "Basic Cauli-Rice", "269", ["Cauliflower"])
    await _add(admin, work, "Curry", "101", ["Basic Cauli-Rice (p. 269)"])
    # As stored before linking existed: lines, no options.
    await adb.execute(text("DELETE FROM ingredient_options"))
    response = await admin.post(f"/api/sources/{work}/references")
    assert response.status_code == 200
    assert response.json() == {"linked": 1}
    assert (await admin.post(f"/api/sources/{work}/references")).json() == {"linked": 1}


async def test_only_an_admin_links_references(client, broker, work) -> None:
    assert (await client.post(f"/api/sources/{work}/references")).status_code == 401
    await _sign_in(client, broker)
    assert (await client.post(f"/api/sources/{work}/references")).status_code == 403


async def test_linking_an_unknown_book_is_a_404(admin) -> None:
    assert (await admin.post(f"/api/sources/{uuid.uuid4()}/references")).status_code == 404
