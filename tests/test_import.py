"""Bulk import: reading the lists, the rules applied per row, and batches.

The CSVs here are made up, in the household index's column layout; the
private files are never used as fixtures.
"""

import time
import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in, make_admins
from openlarder import importer, openlibrary, recipes
from openlarder.models import FlagKind

BOOKS_CSV = (
    "No. of Recipes,Source Title,Author(s),ISBN,Year Published,Focus (If Any),Notes\n"
    "2,Pink Cake,Jo Baker,978-0-393-54111-3,2023,Gluten-Free,\n"
    '1,Family Recipes,"Ann Lee, Bo Lee",,,,\n'
    ",,,,,,\n"
)
RECIPES_CSV = (
    "Source,Tag,Recipe Name,Pg #,Ingredients\n"
    "Pink Cake,Cakes,Rhubarb Cake,112,Rhubarb; Caster Sugar; rhubarb; Egg\n"
    ",,,,\n"
    "Pink Cake,Cakes,Plain Sponge,,Flour; 200g Butter; 269)\n"
    "Family Recipes,Mains,Stew,4,\n"
    "Mystery Book,,Lost Recipe,1,Salt\n"
    ",,,,Flour; Butter\n"
)


# Reading the lists


def test_the_book_list_is_read() -> None:
    books = importer.parse_books(BOOKS_CSV)
    assert [(b.source_title, b.authors, b.isbn13, b.year) for b in books] == [
        ("Pink Cake", ["Jo Baker"], "9780393541113", 2023),
        ("Family Recipes", ["Ann Lee", "Bo Lee"], None, None),
    ]


def test_a_bad_isbn_in_the_book_list_names_its_row() -> None:
    bad = BOOKS_CSV.replace("978-0-393-54111-3", "9780393541114")
    with pytest.raises(importer.UnreadableFile, match="Row 2"):
        importer.parse_books(bad)


def test_a_list_missing_a_column_is_refused() -> None:
    with pytest.raises(importer.UnreadableFile, match="Pg #"):
        importer.parse_recipes("Source,Recipe Name,Ingredients\nA,B,C\n")


def test_the_recipe_list_is_read_and_blank_rows_counted() -> None:
    parsed = importer.parse_recipes(RECIPES_CSV)
    rows = parsed.rows
    assert (parsed.blank, parsed.untitled) == (1, [7])
    assert [(r.row, r.source, r.title, r.page) for r in rows] == [
        (2, "Pink Cake", "Rhubarb Cake", "112"),
        (4, "Pink Cake", "Plain Sponge", None),
        (5, "Family Recipes", "Stew", "4"),
        (6, "Mystery Book", "Lost Recipe", "1"),
    ]
    assert rows[0].lines == ["Rhubarb", "Caster Sugar", "rhubarb", "Egg"]
    # The Tag column is the chapter; a list without it imports none.
    assert [r.chapter for r in rows] == ["Cakes", "Cakes", "Mains", None]
    plain = importer.parse_recipes("Source,Recipe Name,Pg #,Ingredients\nA,B,1,C\n")
    assert plain.rows[0].chapter is None


# The rules applied to one row


E = uuid.uuid4()


def test_a_row_keeps_each_ingredient_once() -> None:
    prepared = importer.prepare("Cake", E, "1", ["Rhubarb", "Flour", "rhubarb"])
    assert prepared.entry.lines == ["Rhubarb", "Flour"]
    assert prepared.flags == []


def test_lines_the_entry_rules_would_change_are_kept_and_flagged() -> None:
    lines = ["Rhubarb", "Sugar", "2 onions, diced", "Pecans (optional)", "Sea Salt"]
    prepared = importer.prepare("Cake", E, "1", lines)
    assert prepared.entry.lines == lines
    assert prepared.flags == [
        (FlagKind.USUALLY_LEFT_OUT, "Sugar"),
        (FlagKind.LINE_DETAIL, "2 onions, diced → onions"),
        (FlagKind.USUALLY_LEFT_OUT, "Pecans (optional)"),
    ]


def test_a_fragment_of_a_split_page_reference_is_flagged_and_dropped() -> None:
    prepared = importer.prepare("Cake", E, "1", ["Flour", "269)", "p. 42)"])
    assert prepared.entry.lines == ["Flour"]
    assert prepared.flags == [(FlagKind.LINE_FRAGMENT, "269)"), (FlagKind.LINE_FRAGMENT, "p. 42)")]


@pytest.mark.parametrize(
    "lines, kept",
    [
        # The household index's two, split where a semicolon was typed for ".".
        (["Garlic", "Chicken Bone Broth (p", "42)"], ["Garlic", "Chicken Bone Broth (p. 42)"]),
        (["Basic Cauli-Rice (p", "269)", "Asparagus"], ["Basic Cauli-Rice (p. 269)", "Asparagus"]),
        (["Stock (pg.", "6)"], ["Stock (pg. 6)"]),
        (["Stock (pp", "xii)"], ["Stock (pp. xii)"]),
    ],
)
def test_a_page_reference_split_by_a_semicolon_is_put_back(lines, kept) -> None:
    prepared = importer.prepare("Cake", E, "1", lines)
    assert prepared.entry.lines == kept
    assert prepared.flags == []


def test_a_lone_page_tail_with_nothing_open_before_it_is_still_a_fragment() -> None:
    prepared = importer.prepare("Cake", E, "1", ["Flour (fine)", "42)"])
    assert prepared.entry.lines == ["Flour (fine)"]
    assert prepared.flags == [(FlagKind.LINE_FRAGMENT, "42)")]


def test_a_line_with_an_amount_is_flagged_and_dropped() -> None:
    prepared = importer.prepare("Cake", E, "1", ["Flour", "200g Butter"])
    assert prepared.entry.lines == ["Flour"]
    assert prepared.flags == [(FlagKind.LINE_REMOVED, "200g Butter: has an amount")]


def test_an_overlong_line_is_flagged_and_dropped() -> None:
    long = "x" * (recipes.MAX_LINE + 1)
    prepared = importer.prepare("Cake", E, "1", ["Flour", long])
    assert prepared.entry.lines == ["Flour"]
    assert [k for k, _ in prepared.flags] == [FlagKind.LINE_REMOVED]


def test_no_ingredients_and_no_page_are_flagged_not_refused() -> None:
    prepared = importer.prepare("Cake", E, None, [])
    assert {k for k, _ in prepared.flags} == {FlagKind.NO_INGREDIENTS, FlagKind.NO_PAGE}


def test_a_row_with_no_title_is_refused() -> None:
    with pytest.raises(recipes.InvalidRecipe):
        importer.prepare("  ", E, "1", ["Flour"])


# Pacing Open Library


async def test_open_library_requests_are_paced(monkeypatch) -> None:
    monkeypatch.setattr(openlibrary, "MIN_INTERVAL", 0.05)
    start = time.monotonic()
    for _ in range(4):
        await openlibrary._wait_turn()
    assert time.monotonic() - start >= 0.15


# Through the routes


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


@pytest.fixture
async def pink_cake(adb):
    work = await adb.scalar(
        text("INSERT INTO sources (title) VALUES ('Love Is a Pink Cake') RETURNING id")
    )
    await adb.execute(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:w, '9780393541113')"), {"w": work}
    )
    return work


def _item(work, row=2, **changes):
    item = {
        "row": row,
        "source_id": str(work),
        "isbn13": "9780393541113",
        "title": "Rhubarb Cake",
        "page": "112",
        "ingredients": ["Rhubarb", "Caster Sugar"],
    }
    return {**item, **changes}


async def test_parse_reports_books_recipe_counts_and_unknown_sources(admin) -> None:
    response = await admin.post(
        "/api/import/parse", json={"books_csv": BOOKS_CSV, "recipes_csv": RECIPES_CSV}
    )
    assert response.status_code == 200
    parsed = response.json()
    assert [(b["source_title"], b["recipes"]) for b in parsed["books"]] == [
        ("Pink Cake", 2),
        ("Family Recipes", 1),
    ]
    assert (parsed["blank_rows"], parsed["untitled_rows"]) == (1, [7])
    assert parsed["unknown_sources"] == ["Mystery Book"]
    assert len(parsed["recipes"]) == 4


async def test_a_batch_stores_recipes_with_their_flags_and_adder(admin, pink_cake, adb) -> None:
    items = [
        _item(pink_cake),
        _item(pink_cake, row=3, title="Plain Sponge", page=None, ingredients=["Flour", "269)"]),
    ]
    result = (await admin.post("/api/import/recipes", json={"items": items})).json()

    assert (result["created"], result["skipped"], result["errors"]) == (2, 0, [])
    assert sorted((f["row"], f["kind"], f["detail"]) for f in result["flags"]) == [
        (3, "line_fragment", "269)"),
        (3, "no_page", None),
    ]
    assert await adb.scalar(text("SELECT count(*) FROM recipe_flags")) == 2
    adders = (await adb.scalars(text("SELECT DISTINCT created_by FROM recipes"))).all()
    assert len(adders) == 1 and adders[0] is not None


async def test_running_a_batch_again_skips_what_it_added(admin, pink_cake, adb) -> None:
    batch = {"items": [_item(pink_cake)]}
    await admin.post("/api/import/recipes", json=batch)
    again = (await admin.post("/api/import/recipes", json=batch)).json()
    assert (again["created"], again["skipped"]) == (0, 1)
    assert await adb.scalar(text("SELECT count(*) FROM recipes")) == 1


async def test_a_chapter_is_stored_and_filled_in_when_run_again(admin, pink_cake, adb) -> None:
    """Recipes imported before chapters were get theirs on the next run;
    one already given a chapter keeps it."""
    await admin.post("/api/import/recipes", json={"items": [_item(pink_cake)]})
    sponge = _item(pink_cake, row=3, title="Sponge", chapter="Cakes")
    await admin.post("/api/import/recipes", json={"items": [sponge]})
    assert await adb.scalar(text("SELECT chapter FROM recipes WHERE title = 'Sponge'")) == "Cakes"
    again = [_item(pink_cake, chapter="Cakes"), {**sponge, "chapter": "Sponges"}]
    result = (await admin.post("/api/import/recipes", json={"items": again})).json()
    assert (result["created"], result["skipped"]) == (0, 2)
    rows = await adb.execute(text("SELECT title, chapter FROM recipes ORDER BY title"))
    assert [tuple(r) for r in rows] == [("Rhubarb Cake", "Cakes"), ("Sponge", "Cakes")]


async def test_the_same_title_on_another_page_is_flagged(admin, pink_cake) -> None:
    await admin.post("/api/import/recipes", json={"items": [_item(pink_cake)]})
    result = (
        await admin.post(
            "/api/import/recipes", json={"items": [_item(pink_cake, row=9, page="140")]}
        )
    ).json()
    assert result["created"] == 1
    assert [(f["kind"], f["detail"]) for f in result["flags"]] == [
        ("duplicate_title", "also on page 112")
    ]


async def test_the_same_title_on_the_same_page_is_kept_and_flagged(admin, pink_cake, adb) -> None:
    """Charcuterie prints two "Basil Cream Sauce I"s on page 291; both are recipes."""
    first = _item(pink_cake, ingredients=["Basic Mayonnaise (p. 277)", "Fresh Basil"])
    second = _item(pink_cake, row=3, ingredients=["Fresh Basil", "Heavy Cream"])
    result = (await admin.post("/api/import/recipes", json={"items": [first, second]})).json()
    assert (result["created"], result["skipped"]) == (2, 0)
    assert [(f["row"], f["kind"], f["detail"]) for f in result["flags"]] == [
        (3, "duplicate_title", "also on page 112")
    ]
    assert await adb.scalar(text("SELECT count(*) FROM recipes")) == 2


async def test_running_again_skips_each_of_two_same_titled_recipes(admin, pink_cake, adb) -> None:
    batch = {
        "items": [
            _item(pink_cake, ingredients=["Fresh Basil", "White Pepper"]),
            _item(pink_cake, row=3, ingredients=["Fresh Basil", "Heavy Cream"]),
        ]
    }
    await admin.post("/api/import/recipes", json=batch)
    again = (await admin.post("/api/import/recipes", json=batch)).json()
    assert (again["created"], again["skipped"]) == (0, 2)
    assert await adb.scalar(text("SELECT count(*) FROM recipes")) == 2


async def test_ingredients_in_another_order_are_another_recipe(admin, pink_cake, adb) -> None:
    await admin.post("/api/import/recipes", json={"items": [_item(pink_cake)]})
    swapped = _item(pink_cake, ingredients=["Caster Sugar", "Rhubarb"])
    result = (await admin.post("/api/import/recipes", json={"items": [swapped]})).json()
    assert (result["created"], result["skipped"]) == (1, 0)


async def test_a_title_repeated_on_two_pages_names_each_once(admin, pink_cake) -> None:
    items = [
        _item(pink_cake, ingredients=["Rhubarb"]),
        _item(pink_cake, row=3, ingredients=["Butter"]),
        _item(pink_cake, row=4, page="140"),
    ]
    result = (await admin.post("/api/import/recipes", json={"items": items})).json()
    assert [(f["row"], f["detail"]) for f in result["flags"]] == [
        (3, "also on page 112"),
        (4, "also on page 112"),
    ]


async def test_a_recipe_whose_book_is_missing_is_an_error_not_a_crash(admin) -> None:
    result = (await admin.post("/api/import/recipes", json={"items": [_item(uuid.uuid4())]})).json()
    assert result["created"] == 0
    assert result["errors"] == [{"row": 2, "reason": "Its book isn't in the catalog yet."}]


async def test_a_batch_is_capped(admin, pink_cake) -> None:
    items = [_item(pink_cake, row=i, title=f"Recipe {i}") for i in range(importer.MAX_BATCH + 1)]
    response = await admin.post("/api/import/recipes", json={"items": items})
    assert response.status_code == 422


async def test_importing_is_for_admins_from_the_site(client, broker, pink_cake) -> None:
    batch = {"items": [_item(pink_cake)]}
    assert (await client.post("/api/import/recipes", json=batch)).status_code == 401
    await _sign_in(client, broker)
    assert (await client.post("/api/import/recipes", json=batch)).status_code == 403
    files = {"books_csv": BOOKS_CSV, "recipes_csv": RECIPES_CSV}
    assert (await client.post("/api/import/parse", json=files)).status_code == 403


async def test_another_sites_page_cannot_import(admin, pink_cake) -> None:
    response = await admin.post(
        "/api/import/recipes",
        json={"items": [_item(pink_cake)]},
        headers={"Origin": "https://auth.openlarder.com"},
    )
    assert response.status_code == 403


# Books without an ISBN


async def test_a_book_without_an_isbn_is_added_once(admin, adb) -> None:
    body = {"title": " Family  Recipes ", "authors": ["Ann Lee", "Bo Lee"], "year": None}
    first = (await admin.post("/api/sources/manual", json=body)).json()
    again = (await admin.post("/api/sources/manual", json=body)).json()

    assert first["existing"] is False and again == {"id": first["id"], "existing": True}
    book = (await admin.get(f"/api/sources/{first['id']}")).json()
    assert book["title"] == "Family Recipes"
    assert [c["credited_as"] for c in book["credits"]] == ["Ann Lee", "Bo Lee"]
    assert len(book["editions"]) == 1


async def test_an_author_without_an_open_library_id_is_reused_by_name(admin, adb) -> None:
    await admin.post("/api/sources/manual", json={"title": "Book One", "authors": ["Ann Lee"]})
    await admin.post("/api/sources/manual", json={"title": "Book Two", "authors": ["ann lee"]})
    assert await adb.scalar(text("SELECT count(*) FROM authors")) == 1


async def test_a_book_without_an_isbn_needs_a_title_and_a_sane_year(admin) -> None:
    assert (await admin.post("/api/sources/manual", json={"title": " "})).status_code == 422
    response = await admin.post("/api/sources/manual", json={"title": "Old", "year": 99})
    assert response.status_code == 422


async def test_a_book_open_library_lacks_keeps_its_isbn(admin, adb) -> None:
    body = {"title": "Heritage", "authors": ["Ann Lee"], "isbn": "978-0-306-40615-7"}
    work = (await admin.post("/api/sources/manual", json=body)).json()["id"]
    assert await adb.scalar(text("SELECT isbn13 FROM editions")) == "9780306406157"
    result = (
        await admin.post(
            "/api/import/recipes",
            json={"items": [_item(work, isbn13="9780306406157", title="Stew", page="4")]},
        )
    ).json()
    assert (result["created"], result["errors"]) == (1, [])


async def test_running_again_gives_an_earlier_isbn_less_book_its_isbn(admin, adb) -> None:
    """What the first household import left: the book, with no ISBN on its edition."""
    first = (await admin.post("/api/sources/manual", json={"title": "Heritage"})).json()["id"]
    again = await admin.post(
        "/api/sources/manual", json={"title": "Heritage", "isbn": "9780306406157"}
    )
    assert again.json() == {"id": first, "existing": True}
    assert await adb.scalar(text("SELECT isbn13 FROM editions")) == "9780306406157"


async def test_a_known_isbn_finds_its_book_whatever_the_title(admin, adb) -> None:
    first = (
        await admin.post("/api/sources/manual", json={"title": "Heritage", "isbn": "9780306406157"})
    ).json()["id"]
    again = await admin.post(
        "/api/sources/manual", json={"title": "Heritage Cookbook", "isbn": "9780306406157"}
    )
    assert again.json() == {"id": first, "existing": True}
    assert await adb.scalar(text("SELECT count(*) FROM sources")) == 1


async def test_a_bad_isbn_for_a_book_without_open_library_is_refused(admin) -> None:
    response = await admin.post(
        "/api/sources/manual", json={"title": "Heritage", "isbn": "9780306406158"}
    )
    assert response.status_code == 422


async def test_recipes_import_into_a_book_without_an_isbn(admin, adb) -> None:
    work = (await admin.post("/api/sources/manual", json={"title": "Family Recipes"})).json()["id"]
    result = (
        await admin.post(
            "/api/import/recipes",
            json={"items": [_item(work, isbn13=None, title="Stew", page="4")]},
        )
    ).json()
    assert (result["created"], result["errors"]) == (1, [])


async def test_each_recipe_goes_on_the_edition_its_isbn_names(admin, pink_cake, adb) -> None:
    # One recipe per ISBN, so picking either edition for both fails, whichever
    # order the database returns them in.
    second = await adb.scalar(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:w, '9780306406157') RETURNING id"),
        {"w": pink_cake},
    )
    first = await adb.scalar(text("SELECT id FROM editions WHERE isbn13 = '9780393541113'"))
    items = [
        _item(pink_cake, row=2, title="On the first", isbn13="9780393541113"),
        _item(pink_cake, row=3, title="On the second", isbn13="9780306406157"),
    ]
    assert (await admin.post("/api/import/recipes", json={"items": items})).json()["created"] == 2
    placed = dict(
        (
            await adb.execute(
                text(
                    "SELECT r.title, p.edition_id FROM recipes r"
                    " JOIN recipe_locations p ON p.recipe_id = r.id"
                )
            )
        ).all()
    )
    assert placed == {"On the first": first, "On the second": second}
