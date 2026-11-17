"""Searching for the recipes that use several ingredients at once."""

import uuid

import pytest
from sqlalchemy import event, text

from fake_broker import _sign_in, make_admins

E = uuid.uuid4()


@pytest.fixture
async def work(adb):
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    await adb.execute(
        text("INSERT INTO editions (id, source_id) VALUES (:id, :w)"), {"id": E, "w": work}
    )
    return work


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
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


async def _id(adb, name):
    return await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": name})


async def _search(client, *ids, **params):
    params = {"ingredient": [str(i) for i in ids], **params}
    return (await client.get("/api/search", params=params)).json()


def _titles(found):
    return [r["title"] for r in found["recipes"]]


async def test_recipes_using_most_of_yours_come_first(admin, work, adb, client) -> None:
    await _add(admin, work, "Rhubarb Crumble", "12", ["Rhubarb", "Butter", "Ginger", "Oats"])
    await _add(admin, work, "Rhubarb Fool", "14", ["Rhubarb", "Cream"])
    await _add(admin, work, "Ginger Biscuits", "30", ["Ginger", "Rhubarb"])
    # Before "Ginger Biscuits" by name, after it by what you have.
    await _add(admin, work, "Candied Ginger", "31", ["Ginger"])
    await _add(admin, work, "Toast", "32", ["Bread"])
    rhubarb, ginger = await _id(adb, "Rhubarb"), await _id(adb, "Ginger")
    found = await _search(client, rhubarb, ginger)
    assert found["ingredients"] == [
        {"id": str(rhubarb), "name": "Rhubarb"},
        {"id": str(ginger), "name": "Ginger"},
    ]
    assert found["missing"] == []
    assert found["total"] == 4
    # Using both of yours before one (Ray, 2026-11-08: frog's legs and
    # garlic should put the recipes with both first); then the most of the
    # recipe you have, then the fewest lines still needed.
    assert [
        (r["title"], r["pages"], r["have"], r["lines"], r["needs"]) for r in found["recipes"]
    ] == [
        ("Ginger Biscuits", ["30"], 2, 2, []),
        # Missing lines in the book's order.
        ("Rhubarb Crumble", ["12"], 2, 4, ["Butter", "Oats"]),
        ("Candied Ginger", ["31"], 1, 1, []),
        ("Rhubarb Fool", ["14"], 1, 2, ["Cream"]),
    ]


async def test_more_of_the_recipe_beats_fewer_lines_missing(admin, work, adb, client) -> None:
    """Having 3 of 5 is closer than 1 of 2, though it needs one more line."""
    await _add(admin, work, "Big Stew", "1", ["Onion", "Carrot", "Celery", "Beef", "Stock"])
    await _add(admin, work, "Buttered Carrots", "2", ["Carrot", "Butter"])
    await _add(admin, work, "Mirepoix", "3", ["Onion", "Carrot", "Celery"])
    have = [await _id(adb, n) for n in ("Onion", "Carrot", "Celery")]
    found = await _search(client, *have)
    assert [(r["title"], r["have"], r["lines"]) for r in found["recipes"]] == [
        ("Mirepoix", 3, 3),
        ("Big Stew", 3, 5),
        ("Buttered Carrots", 1, 2),
    ]


async def test_any_option_on_a_line_covers_it(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", "1", ["Butter or Coconut Oil", "Egg", "Flour"])
    found = await _search(client, await _id(adb, "Coconut Oil"), await _id(adb, "Egg"))
    [cake] = found["recipes"]
    assert (cake["have"], cake["lines"], cake["needs"]) == (2, 3, ["Flour"])


async def test_a_component_is_something_to_make(admin, work, adb, client) -> None:
    await _add(admin, work, "Flour Blend", "10", ["Rice Flour"])
    await _add(admin, work, "Bread", "50", ["Flour Blend (p. 10)", "Egg"])
    found = await _search(client, await _id(adb, "Egg"))
    assert [(r["title"], r["needs"]) for r in found["recipes"]] == [
        ("Bread", ["Flour Blend (p. 10)"])
    ]


async def test_a_recipe_using_one_twice_is_listed_once(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", "1", ["Butter or Margarine", "Margarine"])
    found = await _search(client, await _id(adb, "Margarine"))
    assert (_titles(found), found["total"]) == (["Cake"], 1)
    assert (found["recipes"][0]["have"], found["recipes"][0]["lines"]) == (2, 2)


async def test_an_ingredient_covers_the_ones_under_it(admin, work, adb, client) -> None:
    await _add(admin, work, "Rarebit", "1", ["Aged Cheddar", "Bread"])
    await _add(admin, work, "Toastie", "2", ["Cheese", "Bread"])
    await _add(admin, work, "Salad", "3", ["Lettuce"])
    cheese, aged = await _id(adb, "Cheese"), await _id(adb, "Aged Cheddar")
    cheddar = await adb.scalar(
        text("INSERT INTO ingredients (name, match_key) VALUES ('Cheddar', 'cheddar') RETURNING id")
    )
    parent = "UPDATE ingredients SET parent_id = :p WHERE id = :i"
    await adb.execute(text(parent), {"p": cheese, "i": cheddar})
    await adb.execute(text(parent), {"p": cheddar, "i": aged})
    found = await _search(client, cheese, await _id(adb, "Bread"))
    assert [(r["title"], r["needs"]) for r in found["recipes"]] == [
        ("Rarebit", []),
        ("Toastie", []),
    ]
    # Not upward: having aged cheddar isn't having any cheese.
    assert [(r["title"], r["needs"]) for r in (await _search(client, aged))["recipes"]] == [
        ("Rarebit", ["Bread"])
    ]


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
    monkeypatch.setattr("openlarder.routers.search.PAGE", 2)
    for n in range(5):
        await _add(admin, work, f"Cake {n}", str(n), ["Egg"])
    egg = await _id(adb, "Egg")
    first = await _search(client, egg)
    rest = await _search(client, egg, offset=4)
    assert (_titles(first), first["total"]) == (["Cake 0", "Cake 1"], 5)
    assert _titles(rest) == ["Cake 4"]
    by_title = await _search(client, q="cake", offset=2)
    assert (_titles(by_title), by_title["total"]) == (["Cake 2", "Cake 3"], 5)


async def test_a_search_has_limits(client) -> None:
    assert (await client.get("/api/search")).status_code == 422
    ids = lambda n: [str(uuid.uuid4()) for _ in range(n)]  # noqa: E731
    for name, most in (("ingredient", 30), ("source", 10)):
        extra = {} if name == "ingredient" else {"q": "cake"}
        ok = await client.get("/api/search", params={name: ids(most), **extra})
        assert ok.status_code == 200
        over = await client.get("/api/search", params={name: ids(most + 1), **extra})
        assert over.status_code == 422


async def test_a_page_not_recorded_is_left_off(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", None, ["Egg"])
    found = await _search(client, await _id(adb, "Egg"))
    assert [r["pages"] for r in found["recipes"]] == [[]]


# Within one book


async def _other_book(adb):
    other = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Plenty') RETURNING id"))
    edition = uuid.uuid4()
    await adb.execute(
        text("INSERT INTO editions (id, source_id) VALUES (:id, :w)"), {"id": edition, "w": other}
    )
    return other, edition


async def test_a_search_can_stay_in_some_books(admin, work, adb, client) -> None:
    other, edition = await _other_book(adb)
    third = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Jerusalem') RETURNING id"))
    await _add(admin, work, "Rhubarb Cake", "1", ["Rhubarb", "Egg"])
    for book, title in ((other, "Rhubarb Salad"), (third, "Rhubarb Tart")):
        edition = await adb.scalar(
            text("INSERT INTO editions (source_id) VALUES (:w) RETURNING id"), {"w": book}
        )
        response = await admin.post(
            f"/api/sources/{book}/recipes",
            json={
                "title": title,
                "editions": [{"edition_id": str(edition), "page": "9"}],
                "ingredients": ["Rhubarb"],
            },
        )
        assert response.status_code == 201
    rhubarb = await _id(adb, "Rhubarb")
    everywhere = await _search(client, rhubarb)
    assert (everywhere["sources"], everywhere["total"]) == ([], 3)
    found = await _search(client, rhubarb, source=[str(third), str(other)])
    assert found["sources"] == [
        {"id": str(third), "name": "Jerusalem"},
        {"id": str(other), "name": "Plenty"},
    ]
    # By book: Jerusalem, then Plenty.
    assert _titles(found) == ["Rhubarb Tart", "Rhubarb Salad"]


async def test_an_unknown_book_is_reported_and_left_out(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", "1", ["Egg"])
    gone = uuid.uuid4()
    found = await _search(client, await _id(adb, "Egg"), source=[str(gone), str(work)])
    assert (found["missing_sources"], [b["name"] for b in found["sources"]]) == (
        [str(gone)],
        ["Pink Cake"],
    )
    assert _titles(found) == ["Cake"]


async def test_a_book_lists_the_ingredients_it_uses_most(admin, work, adb, client) -> None:
    other, edition = await _other_book(adb)
    await _add(admin, work, "A", "1", ["Egg", "Butter or Margarine", "Margarine"])
    await _add(admin, work, "B", "2", ["Egg", "Flour"])
    await _add(admin, work, "C", "3", ["Butter"])
    await _add(admin, work, "D", "4", ["Margarine"])
    for title in ("X", "Y", "Z"):
        await admin.post(
            f"/api/sources/{other}/recipes",
            json={
                "title": title,
                "editions": [{"edition_id": str(edition)}],
                "ingredients": ["Flour"],
            },
        )
    book = (await client.get(f"/api/sources/{work}")).json()
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
    book = (await client.get(f"/api/sources/{work}")).json()
    assert [i["name"] for i in book["ingredients"]] == [f"Spice {n:02}" for n in range(30)]


# By title


async def test_every_title_word_must_appear(admin, work, client) -> None:
    await _add(admin, work, "Rhubarb and Ginger Cake", "1", ["Rhubarb"])
    await _add(admin, work, "Rhubarb Fool", "2", ["Rhubarb"])
    await _add(admin, work, "Carrot Cake", "3", ["Carrot"])
    found = await _search(client, q="  CAKE rhubarb ")
    assert (_titles(found), found["q"]) == (["Rhubarb and Ginger Cake"], "CAKE rhubarb")
    assert _titles(await _search(client, q="cake")) == ["Carrot Cake", "Rhubarb and Ginger Cake"]


async def test_title_words_narrow_an_ingredient_search(admin, work, adb, client) -> None:
    await _add(admin, work, "Rhubarb Cake", "1", ["Rhubarb", "Egg"])
    await _add(admin, work, "Rhubarb Fool", "2", ["Rhubarb", "Cream"])
    await _add(admin, work, "Lemon Cake", "3", ["Egg"])
    egg = await _id(adb, "Egg")
    assert _titles(await _search(client, egg, q="rhubarb")) == ["Rhubarb Cake"]


async def test_title_words_within_a_book(admin, work, adb, client) -> None:
    other, edition = await _other_book(adb)
    await _add(admin, work, "Rhubarb Cake", "1", ["Rhubarb"])
    await admin.post(
        f"/api/sources/{other}/recipes",
        json={
            "title": "Rhubarb Salad",
            "editions": [{"edition_id": str(edition)}],
            "ingredients": ["Rhubarb"],
        },
    )
    assert _titles(await _search(client, q="rhubarb", source=str(other))) == ["Rhubarb Salad"]


async def test_wildcards_in_a_title_are_typed_characters(admin, work, client) -> None:
    await _add(admin, work, "100% Rye Bread", "1", ["Rye Flour"])
    await _add(admin, work, "Rye_Crackers", "2", ["Rye Flour"])
    await _add(admin, work, "Seeded Bread", "3", ["Seeds"])
    assert _titles(await _search(client, q="%")) == ["100% Rye Bread"]
    assert _titles(await _search(client, q="_")) == ["Rye_Crackers"]


async def test_title_words_still_search_when_the_ingredient_is_gone(admin, work, client) -> None:
    await _add(admin, work, "Rhubarb Cake", "1", ["Rhubarb"])
    found = await _search(client, uuid.uuid4(), q="cake")
    assert (_titles(found), len(found["missing"])) == (["Rhubarb Cake"], 1)


async def test_a_title_search_has_at_most_ten_words(client) -> None:
    assert (
        await client.get("/api/search", params={"q": " ".join("abcdefghij")})
    ).status_code == 200
    assert (
        await client.get("/api/search", params={"q": " ".join("abcdefghijk")})
    ).status_code == 422


# Where each found recipe is, and narrowing by kind of source


async def test_a_hit_says_where_it_is(admin, work, adb, client) -> None:
    author = await adb.scalar(
        text(
            "INSERT INTO authors (name, name_key)"
            " VALUES ('Claire Ptak', 'claire ptak') RETURNING id"
        )
    )
    await adb.execute(
        text(
            "INSERT INTO source_credits (source_id, author_id, position, credited_as)"
            " VALUES (:w, :a, 1, 'Claire Ptak')"
        ),
        {"w": work, "a": author},
    )
    await _add(admin, work, "Rhubarb Cake", "12", ["Rhubarb"])
    magazine = (
        await admin.post("/api/sources/periodicals", json={"kind": "magazine", "title": "Saveur"})
    ).json()["id"]
    await admin.post(
        f"/api/sources/{magazine}/recipes",
        json={
            "title": "Rhubarb Fool",
            "issue": "May 2024",
            "issue_page": "42",
            "ingredients": ["Rhubarb"],
        },
    )
    show = (
        await admin.post("/api/sources/shows", json={"kind": "tv_show", "title": "Salt Fat"})
    ).json()["id"]
    await admin.post(
        f"/api/sources/{show}/recipes",
        json={
            "title": "Rhubarb Jam",
            "episode": {"season": 1, "number": 2, "at": "12:34"},
            "ingredients": ["Rhubarb"],
        },
    )
    site = (await admin.post("/api/sources/websites", json={"address": "example.com"})).json()
    await admin.post(
        f"/api/sources/{site['id']}/recipes",
        json={
            "title": "Rhubarb Tart",
            "web_address": "https://example.com/tart",
            "ingredients": ["Rhubarb"],
        },
    )
    found = await _search(client, await _id(adb, "Rhubarb"))
    where = {
        r["title"]: (
            r["source_kind"],
            r["authors"],
            r["pages"],
            r["issue"],
            r["episode"],
            r["at"],
            r["site"],
        )
        for r in found["recipes"]
    }
    assert where == {
        "Rhubarb Cake": ("book", ["Claire Ptak"], ["12"], None, None, None, None),
        "Rhubarb Fool": ("magazine", [], ["42"], "May 2024", None, None, None),
        "Rhubarb Jam": ("tv_show", [], [], None, "Season 1, episode 2", "12:34", None),
        "Rhubarb Tart": ("website", [], [], None, None, None, "example.com"),
    }
    assert found["per_page"] > 0


async def test_kinds_narrow_a_search(admin, work, adb, client) -> None:
    await _add(admin, work, "Rhubarb Cake", "12", ["Rhubarb"])
    magazine = (
        await admin.post("/api/sources/periodicals", json={"kind": "magazine", "title": "Saveur"})
    ).json()["id"]
    await admin.post(
        f"/api/sources/{magazine}/recipes",
        json={"title": "Rhubarb Fool", "issue": "May", "ingredients": ["Rhubarb"]},
    )
    rhubarb = await _id(adb, "Rhubarb")
    assert _titles(await _search(client, rhubarb, kind=["magazine"])) == ["Rhubarb Fool"]
    assert _titles(await _search(client, rhubarb, kind=["book", "magazine"])) == [
        "Rhubarb Cake",
        "Rhubarb Fool",
    ]
    assert _titles(await _search(client, q="rhubarb", kind=["book"])) == ["Rhubarb Cake"]
    bad = await client.get("/api/search", params={"q": "rhubarb", "kind": ["zine"]})
    assert bad.status_code == 422


async def test_the_apps_connections_run_without_jit(database_url) -> None:
    """JIT compiling cost a search three times its running time."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from openlarder import db

    engine = create_async_engine(database_url, connect_args=db.CONNECT_ARGS)
    try:
        async with engine.connect() as conn:
            assert await conn.scalar(text("SHOW jit")) == "off"
    finally:
        await engine.dispose()


def test_the_apps_engine_uses_those_connection_settings(monkeypatch) -> None:
    from openlarder import db

    made = {}
    monkeypatch.setattr(db, "create_async_engine", lambda url, **kw: made.update(kw) or "engine")
    monkeypatch.setattr(db, "_engine", None)
    assert db.get_engine() == "engine"
    assert made["connect_args"] == db.CONNECT_ARGS


async def test_a_hit_says_which_of_yours_it_uses(admin, work, adb, client) -> None:
    """By the names you chose, in your order: cheddar counts as cheese."""
    await _add(admin, work, "Cheese Scones", "1", ["Aged Cheddar", "Onion", "Flour"])
    await _add(admin, work, "Onion Powder", "2", ["Onion"])
    await _add(admin, work, "Cheese Board", "3", ["Cheese"])
    cheese, cheddar = await _id(adb, "Cheese"), await _id(adb, "Aged Cheddar")
    await adb.execute(
        text("UPDATE ingredients SET parent_id = :p WHERE id = :i"), {"p": cheese, "i": cheddar}
    )
    onion = await _id(adb, "Onion")
    found = await _search(client, cheese, onion)
    assert {r["title"]: r["uses"] for r in found["recipes"]} == {
        "Cheese Scones": ["Cheese", "Onion"],
        "Onion Powder": ["Onion"],
        "Cheese Board": ["Cheese"],
    }


# Leaving out what you don't have or want


async def test_a_recipe_needing_an_unwanted_ingredient_is_left_out(admin, work, adb, client):
    await _add(admin, work, "Butter Cake", "1", ["Flour", "Butter"])
    await _add(admin, work, "Oil Cake", "2", ["Flour", "Butter or Coconut Oil"])
    await _add(admin, work, "Plain Cake", "3", ["Flour"])
    await _add(admin, work, "Cheese Cake", "4", ["Flour", "Aged Cheddar"])
    flour, butter = await _id(adb, "Flour"), await _id(adb, "Butter")
    await _add(admin, work, "Cheese Plate", "5", ["Cheese"])
    cheese, cheddar = await _id(adb, "Cheese"), await _id(adb, "Aged Cheddar")
    await adb.execute(
        text("UPDATE ingredients SET parent_id = :p WHERE id = :i"), {"p": cheese, "i": cheddar}
    )
    found = await _search(client, flour, without=[str(butter), str(cheese)])
    # Butter Cake needs butter; Oil Cake can use the oil; cheddar is cheese.
    assert sorted(_titles(found)) == ["Oil Cake", "Plain Cake"]
    assert [w["name"] for w in found["without"]] == ["Butter", "Cheese"]
    by_title = await _search(client, q="cake", without=[str(butter)])
    assert sorted(_titles(by_title)) == ["Cheese Cake", "Oil Cake", "Plain Cake"]


async def test_an_unwanted_ingredient_gone_is_reported(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", "1", ["Flour"])
    gone = uuid.uuid4()
    found = await _search(client, await _id(adb, "Flour"), without=[str(gone)])
    assert (found["missing"], _titles(found)) == ([str(gone)], ["Cake"])


async def test_only_what_you_can_make(admin, work, adb, client) -> None:
    """missing_max keeps the recipes missing at most that many lines (Ray,
    2026-11-14); without it, ingredients rank and don't filter."""
    await _add(admin, work, "Ginger Biscuits", "30", ["Ginger", "Rhubarb"])
    await _add(admin, work, "Rhubarb Fool", "14", ["Rhubarb", "Cream"])
    await _add(admin, work, "Rhubarb Crumble", "12", ["Rhubarb", "Butter", "Ginger", "Oats"])
    await _add(admin, work, "Rhubarb Trifle", "16", ["Rhubarb", "Cream", "Sponge", "Custard"])
    # Either of its choices covers the line.
    await _add(admin, work, "Rhubarb Syrup", "18", ["Rhubarb", "Ginger or Vanilla"])
    await _add(admin, work, "Toast", "32", ["Bread"])
    rhubarb, ginger = await _id(adb, "Rhubarb"), await _id(adb, "Ginger")

    everything = await _search(client, rhubarb, ginger)
    assert everything["total"] == 5
    make_now = await _search(client, rhubarb, ginger, missing_max=0)
    assert sorted(_titles(make_now)) == ["Ginger Biscuits", "Rhubarb Syrup"]
    assert make_now["total"] == 2
    assert all(r["needs"] == [] and r["have"] == r["lines"] for r in make_now["recipes"])
    one = await _search(client, rhubarb, ginger, missing_max=1)
    assert sorted(_titles(one)) == ["Ginger Biscuits", "Rhubarb Fool", "Rhubarb Syrup"]
    two = await _search(client, rhubarb, ginger, missing_max=2)
    assert sorted(_titles(two)) == [
        "Ginger Biscuits",
        "Rhubarb Crumble",
        "Rhubarb Fool",
        "Rhubarb Syrup",
    ]
    assert two["total"] == 4
    # In the order they'd come anyway.
    assert _titles(two) == [t for t in _titles(everything) if t in _titles(two)]
    # With title words too.
    fool = await _search(client, rhubarb, ginger, missing_max=1, q="fool")
    assert _titles(fool) == ["Rhubarb Fool"]


async def test_a_component_counts_as_missing(admin, work, adb, client) -> None:
    await _add(admin, work, "Flour Blend", "10", ["Rice Flour"])
    await _add(admin, work, "Bread", "50", ["Flour Blend (p. 10)", "Egg"])
    await _add(admin, work, "Omelette", "51", ["Egg"])
    egg = await _id(adb, "Egg")
    assert _titles(await _search(client, egg, missing_max=0)) == ["Omelette"]
    assert sorted(_titles(await _search(client, egg, missing_max=1))) == ["Bread", "Omelette"]


async def test_missing_max_is_nought_one_or_two_and_needs_ingredients(
    admin, work, adb, client
) -> None:
    await _add(admin, work, "Rhubarb Fool", "14", ["Rhubarb", "Cream"])
    rhubarb = await _id(adb, "Rhubarb")
    for wrong in (3, -1, "few"):
        response = await client.get(
            "/api/search", params={"ingredient": str(rhubarb), "missing_max": wrong}
        )
        assert response.status_code == 422
    # A title alone has nothing to count: it finds what it would.
    by_title = (await client.get("/api/search", params={"q": "fool", "missing_max": 0})).json()
    assert _titles(by_title) == ["Rhubarb Fool"]
    # And it isn't something to search by.
    alone = await client.get("/api/search", params={"missing_max": 0})
    assert alone.status_code == 422


async def _offered(c, q, **params):
    """What the search page's boxes offer for what's typed, in order, each
    with its count."""
    response = await c.get("/api/ingredients", params={"q": q, "under": "true", **params})
    assert response.status_code == 200, response.text
    return {i["name"]: i["recipes"] for i in response.json()["ingredients"]}


async def test_a_box_counts_what_choosing_an_ingredient_finds(
    admin, work, adb, client, people
) -> None:
    """It counted the recipes using exactly that ingredient, so "Cheese"
    said 1 recipe and found three."""
    await _add(admin, work, "Rarebit", "1", ["Aged Cheddar", "Bread"])
    await _add(admin, work, "Toastie", "2", ["Cheese", "Bread"])
    await _add(admin, work, "Ploughman's", "3", ["Cheddar", "Aged Cheddar"])
    await _add(admin, work, "Cheesecake", "4", ["Cream Cheese", "Egg"])
    cheese, cheddar, aged = [await _id(adb, n) for n in ("Cheese", "Cheddar", "Aged Cheddar")]
    parent = "UPDATE ingredients SET parent_id = :p WHERE id = :i"
    await adb.execute(text(parent), {"p": cheese, "i": cheddar})
    await adb.execute(text(parent), {"p": cheddar, "i": aged})

    offered = await _offered(client, "che")
    # Cheese's are cheddar's and aged cheddar's too, each recipe once (the
    # ploughman's uses both); cream cheese has "cheese" in it and isn't
    # under it. The most found first, where by the recipes naming it cheese
    # came after aged cheddar.
    assert offered == {"Cheese": 3, "Aged Cheddar": 2, "Cheddar": 2, "Cream Cheese": 1}
    assert list(offered)[0] == "Cheese"
    for name, count in offered.items():
        assert (await _search(client, await _id(adb, name)))["total"] == count, name
    # Without it, the list is as it was: the recipes naming each.
    exact = (await client.get("/api/ingredients", params={"q": "che"})).json()["ingredients"]
    assert {i["name"]: i["recipes"] for i in exact} == {
        "Aged Cheddar": 2,
        "Cheddar": 1,
        "Cheese": 1,
        "Cream Cheese": 1,
    }
    # The names asked for by name are counted the same way.
    named = await client.get("/api/ingredients", params={"name": "cheese", "under": "true"})
    assert [(i["name"], i["recipes"]) for i in named.json()["ingredients"]] == [("Cheese", 3)]
    # A family's recipe is counted for them and for nobody else.
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    made = await ann.post(
        f"/api/sources/{box}/recipes", json={"title": "Nana's", "ingredients": ["aged cheddar"]}
    )
    assert made.status_code == 201, made.text
    hers = await _offered(ann, "che")
    assert hers == {"Cheese": 4, "Aged Cheddar": 3, "Cheddar": 3, "Cream Cheese": 1}
    for other in (client, await people("mo", role="moderator")):
        assert await _offered(other, "che") == offered


async def test_a_boxs_counting_starts_from_what_was_typed(client, async_engine) -> None:
    """What's said to the database, since the answer is the same either
    way: the families counted are those of what the typing matches, not of
    every ingredient or thing there is. The box asks at each letter."""
    said: list[str] = []

    def note(conn, cursor, statement, parameters, context, executemany) -> None:
        said.append(" ".join(statement.split()))

    event.listen(async_engine.sync_engine, "before_cursor_execute", note)
    try:
        for what in ("ingredients", "equipment"):
            said.clear()
            found = await client.get(f"/api/{what}", params={"q": "che", "under": "true"})
            assert found.status_code == 200, found.text
            counted = [q for q in said if "WITH RECURSIVE under_each" in q]
            assert counted, what
            for q in counted:
                # The family's start, before what's under it is added.
                assert " ILIKE " in q.split(" UNION ")[0], (what, q)
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", note)
