"""Ratings (routers/ratings.py): one to five spoons, shown as an average."""

from sqlalchemy import text


async def _recipe(mo, adb, title="Barley Soup"):
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty"})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={"title": title, "editions": [{"edition_id": edition, "page": "12"}]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_spoons_are_averaged_and_never_say_who(people, client, adb) -> None:
    mo, ann, bo = await people("mo", role="moderator"), await people("ann"), await people("bo")
    soup = await _recipe(mo, adb)
    url = f"/api/recipes/{soup}/rating"

    assert (await client.get(url)).json() == {"spoons": None, "ratings": 0, "mine": None}
    assert (await ann.put(url, json={"spoons": 5})).json() == {
        "spoons": 5.0,
        "ratings": 1,
        "mine": 5,
    }
    assert (await bo.put(url, json={"spoons": 2})).json() == {
        "spoons": 3.5,
        "ratings": 2,
        "mine": 2,
    }
    # Changing yours is still one rating.
    assert (await bo.put(url, json={"spoons": 4})).json()["spoons"] == 4.5
    # Signed out: the average, and nothing of whose.
    assert (await client.get(url)).json() == {"spoons": 4.5, "ratings": 2, "mine": None}
    assert (await mo.get(url)).json()["mine"] is None

    for bad in (0, 6, 2.5):
        assert (await ann.put(url, json={"spoons": bad})).status_code == 422
    assert (await client.put(url, json={"spoons": 3})).status_code == 401

    # A listing carries it.
    [hit] = (await client.get("/api/search", params={"q": "barley"})).json()["recipes"]
    assert (hit["spoons"], hit["ratings"]) == (4.5, 2)

    assert (await bo.delete(url)).status_code == 204
    assert (await client.get(url)).json() == {"spoons": 5.0, "ratings": 1, "mine": None}


async def test_a_private_recipe_is_rated_only_by_who_sees_it(people, client) -> None:
    ann, bo = await people("ann"), await people("bo")
    box = (
        await ann.post("/api/sources/family", json={"title": "Gran's Box", "acknowledged": True})
    ).json()["id"]
    fudge = (
        await ann.post(f"/api/sources/{box}/recipes", json={"title": "Fudge", "ingredients": []})
    ).json()["id"]
    url = f"/api/recipes/{fudge}/rating"
    assert (await ann.put(url, json={"spoons": 5})).status_code == 200
    assert (await bo.get(url)).status_code == 404
    assert (await bo.put(url, json={"spoons": 1})).status_code == 404
    assert (await client.get(url)).status_code == 404


async def test_deleting_the_account_takes_its_ratings(people, client, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    soup = await _recipe(mo, adb)
    await ann.put(f"/api/recipes/{soup}/rating", json={"spoons": 1})
    assert (await ann.post("/api/account/delete", json={"confirm": "ann"})).status_code == 204
    assert (await client.get(f"/api/recipes/{soup}/rating")).json()["ratings"] == 0


# Ratings rank (Ray, 2026-11-12)


async def _rated(people, adb, spoons_by_title, authors=("Yotam Ottolenghi",)):
    """A book with a recipe of each title, given these spoons by as many
    people; returns the book, its author and the recipes by title."""
    mo = await people("mo", role="moderator")
    book = (
        await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": list(authors)})
    ).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    raters = [await people(f"rater{n}") for n in range(max(map(len, spoons_by_title.values())))]
    recipes = {}
    for page, (title, spoons) in enumerate(spoons_by_title.items(), start=1):
        made = await mo.post(
            f"/api/sources/{book}/recipes",
            json={
                "title": title,
                "editions": [{"edition_id": edition, "page": str(page)}],
                "ingredients": ["Garlic"] if "Garlic" in title else ["Leek", "Onion"],
            },
        )
        assert made.status_code == 201, made.text
        recipes[title] = made.json()["id"]
        for rater, given in zip(raters, spoons, strict=False):
            rated = await rater.put(
                f"/api/recipes/{made.json()['id']}/rating", json={"spoons": given}
            )
            assert rated.status_code == 200, rated.text
    return book, recipes


async def test_a_sources_page_and_an_authors_show_their_top_rated(people, client, adb) -> None:
    book, _ = await _rated(
        people,
        adb,
        {
            # Shown, and weighed: as if two more people gave three spoons.
            "Good Soup": [4, 5],  # 4.5, weighed 3.75
            "Best Bread": [5, 5],  # 5.0, weighed 4.0
            "Fine Cake": [5],  # 5.0 from one, weighed 3.67: after Good Soup's 4.5 from two
            "Fair Stew": [3, 5],  # 4.0: just in, weighed 3.5
            "Poor Pie": [3],  # under four spoons
            "Almost Tart": [4, 4, 3],  # 3.7: shown as under four, so not in
            "Plain Rice": [],
        },
    )
    shown = (await client.get(f"/api/sources/{book}")).json()
    assert [(r["title"], r["spoons"], r["ratings"], r["pages"]) for r in shown["top_rated"]] == [
        ("Best Bread", 5.0, 2, ["2"]),
        ("Good Soup", 4.5, 2, ["1"]),
        ("Fine Cake", 5.0, 1, ["3"]),
        ("Fair Stew", 4.0, 2, ["4"]),
    ]
    author = shown["credits"][0]["author_id"]
    theirs = (await client.get(f"/api/authors/{author}")).json()["top_rated"]
    assert [(r["title"], r["source_title"]) for r in theirs] == [
        ("Best Bread", "Plenty"),
        ("Good Soup", "Plenty"),
        ("Fine Cake", "Plenty"),
        ("Fair Stew", "Plenty"),
    ]


async def test_top_rated_is_the_best_five_and_left_off_with_none(people, client, adb) -> None:
    book, _ = await _rated(people, adb, {f"Dish {n}": [5] for n in range(7)} | {"Plain": []})
    shown = (await client.get(f"/api/sources/{book}")).json()
    # Level on spoons and on how many: by title.
    assert [r["title"] for r in shown["top_rated"]] == [f"Dish {n}" for n in range(5)]
    mo = await people("mo2", role="moderator")
    bare = (await mo.post("/api/sources/manual", json={"title": "Unrated Book"})).json()["id"]
    assert (await client.get(f"/api/sources/{bare}")).json()["top_rated"] == []


async def test_top_rated_waits_for_three_rated_recipes(people, client, adb) -> None:
    """Ray's spec, 2026-11-13: "only when at least three recipes have
    ratings". Rated at all, not rated well: the third here has two spoons."""
    book, recipes = await _rated(
        people, adb, {"Best Bread": [5, 5], "Good Soup": [4], "Poor Pie": [], "Plain Rice": []}
    )
    shown = (await client.get(f"/api/sources/{book}")).json()
    author = shown["credits"][0]["author_id"]
    assert shown["top_rated"] == []
    assert (await client.get(f"/api/authors/{author}")).json()["top_rated"] == []
    # The recipes still say what they were given.
    assert (await client.get(f"/api/recipes/{recipes['Best Bread']}/rating")).json()["spoons"] == 5
    rater = await people("latecomer")
    assert (
        await rater.put(f"/api/recipes/{recipes['Poor Pie']}/rating", json={"spoons": 2})
    ).status_code == 200
    shown = (await client.get(f"/api/sources/{book}")).json()
    assert [r["title"] for r in shown["top_rated"]] == ["Best Bread", "Good Soup"]
    theirs = (await client.get(f"/api/authors/{author}")).json()["top_rated"]
    assert [r["title"] for r in theirs] == ["Best Bread", "Good Soup"]


async def test_one_five_doesnt_top_a_list_others_have_rated_more(people, client, adb) -> None:
    """Ray's spec, 2026-11-13: "a damped average so a single 5 does not top
    the list". What's shown is still each recipe's plain average."""
    book, _ = await _rated(
        people,
        adb,
        {
            "Lone Five": [5],  # weighed (5 + 6) / 3 = 3.67
            "Steady": [5, 4, 5, 4],  # 4.5, weighed (18 + 6) / 6 = 4.0
            "Nearly": [4, 5],  # 4.5, weighed (9 + 6) / 4 = 3.75
            "Lone Four": [4],  # weighed (4 + 6) / 3 = 3.33
        },
    )
    shown = (await client.get(f"/api/sources/{book}")).json()
    assert [(r["title"], r["spoons"], r["ratings"]) for r in shown["top_rated"]] == [
        ("Steady", 4.5, 4),
        ("Nearly", 4.5, 2),
        ("Lone Five", 5.0, 1),
        ("Lone Four", 4.0, 1),
    ]


async def test_a_search_can_put_the_rated_first(people, client, adb) -> None:
    book, _ = await _rated(
        people,
        adb,
        {
            "Apple Soup": [],
            "Barley Soup": [4],
            "Carrot Soup": [5, 5],
            "Dill Soup": [5],
            "Egg Soup": [],
        },
    )
    # No title words, so nothing ranks by title (test_title_rank.py): by book
    # and title, as a search by tag or ingredient page lists them.
    tag = str(await adb.scalar(text("SELECT id FROM tags WHERE name = 'Soup'")))
    tagged = await (await people("mo2", role="moderator")).put(
        f"/api/sources/{book}/tags", json={"tags": [tag]}
    )
    assert tagged.status_code == 200, tagged.text
    usual = (await client.get("/api/search", params={"tag": tag})).json()
    assert [r["title"] for r in usual["recipes"]] == [
        "Apple Soup",
        "Barley Soup",
        "Carrot Soup",
        "Dill Soup",
        "Egg Soup",
    ]
    best = (await client.get("/api/search", params={"tag": tag, "sort": "rating"})).json()
    # The rated ones, best first; then the rest as they'd come anyway.
    assert [r["title"] for r in best["recipes"]] == [
        "Carrot Soup",
        "Dill Soup",
        "Barley Soup",
        "Apple Soup",
        "Egg Soup",
    ]
    assert best["total"] == usual["total"] == 5
    assert (await client.get("/api/search", params={"q": "soup", "sort": "x"})).status_code == 422


async def test_rating_comes_before_how_well_ingredients_match(people, client, adb) -> None:
    """Sorted by rating, a rated recipe using one of your ingredients comes
    before an unrated one using them all: that's what was asked for."""
    _, recipes = await _rated(people, adb, {"Leek Tart": [], "Garlic Paste": [5], "Leek Soup": [4]})
    named = {
        n: str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": n}))
        for n in ("Leek", "Onion", "Garlic")
    }
    asked = {"ingredient": [named["Leek"], named["Onion"], named["Garlic"]]}
    usual = (await client.get("/api/search", params=asked)).json()
    assert [r["title"] for r in usual["recipes"]] == ["Leek Soup", "Leek Tart", "Garlic Paste"]
    best = (await client.get("/api/search", params={**asked, "sort": "rating"})).json()
    assert [r["title"] for r in best["recipes"]] == ["Garlic Paste", "Leek Soup", "Leek Tart"]
    assert [r["have"] for r in best["recipes"]] == [1, 2, 2]
    # Paged the same way.
    assert best["total"] == 3
