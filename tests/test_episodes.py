"""TV shows, podcasts and video channels as sources, and recipes in their
episodes."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET is_admin = true"))
    return client


async def _show(client, title="Salt Fat Acid Heat", kind="tv_show", **more):
    response = await client.post("/api/sources/shows", json={"kind": kind, "title": title, **more})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _recipe(client, source, title, ingredients=("Rhubarb",), **where):
    return await client.post(
        f"/api/sources/{source}/recipes",
        json={"title": title, "ingredients": list(ingredients), **where},
    )


async def _episode(client, recipe_id):
    return (await client.get(f"/api/recipes/{recipe_id}")).json()["episode"]


# Adding one


async def test_a_show_is_added_once_by_name_and_kind(admin, client) -> None:
    first = await admin.post(
        "/api/sources/shows",
        json={"kind": "tv_show", "title": " Salt  Fat Acid Heat ", "authors": ["Samin Nosrat"]},
    )
    again = await admin.post(
        "/api/sources/shows", json={"kind": "tv_show", "title": "salt fat acid heat"}
    )
    assert (first.json()["existing"], again.json()) == (
        False,
        {"id": first.json()["id"], "existing": True},
    )
    podcast = await _show(admin, "Salt Fat Acid Heat", kind="podcast")
    assert podcast != first.json()["id"]
    shown = (await client.get(f"/api/sources/{first.json()['id']}")).json()
    assert (shown["kind"], shown["title"], shown["episodes"]) == (
        "tv_show",
        "Salt Fat Acid Heat",
        [],
    )
    assert [c["credited_as"] for c in shown["credits"]] == ["Samin Nosrat"]


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "tv_show", "title": " "},
        {"kind": "magazine", "title": "Saveur"},
        {"kind": "radio", "title": "The Splendid Table"},
    ],
)
async def test_a_bad_show_is_refused(admin, body) -> None:
    assert (await admin.post("/api/sources/shows", json=body)).status_code == 422


async def test_only_admins_add_shows(admin, adb) -> None:
    await adb.execute(text("UPDATE users SET is_admin = false"))
    response = await admin.post("/api/sources/shows", json={"kind": "podcast", "title": "X"})
    assert response.status_code == 403


# Recipes in episodes


async def test_a_recipe_is_in_an_episode_at_a_time(admin, client) -> None:
    source = await _show(admin)
    made = await _recipe(
        admin,
        source,
        "Buttermilk Chicken",
        episode={
            "season": 1,
            "number": 2,
            "title": " Salt ",
            "aired_on": "2018-10-11",
            "at": "12:34",
        },
    )
    assert made.status_code == 201, made.text
    recipe = (await client.get(f"/api/recipes/{made.json()['id']}")).json()
    assert recipe["source"]["kind"] == "tv_show"
    episode = recipe["episode"]
    assert (episode["name"], episode["aired_on"], episode["at"]) == (
        "Season 1, episode 2, “Salt”",
        "2018-10-11",
        "12:34",
    )
    assert (recipe["pages"], recipe["web_address"], recipe["issue"]) == ([], None, None)
    shown = (await client.get(f"/api/sources/{source}")).json()
    assert [e["name"] for e in shown["episodes"]] == ["Season 1, episode 2, “Salt”"]
    assert [(r["title"], r["episode"], r["at"]) for r in shown["recipes"]] == [
        ("Buttermilk Chicken", "Season 1, episode 2, “Salt”", "12:34")
    ]


async def test_recipes_share_an_episode_by_number_title_or_address(admin, adb) -> None:
    show = await _show(admin)
    await _recipe(admin, show, "A", episode={"season": 1, "number": 2})
    await _recipe(admin, show, "B", episode={"season": 1, "number": 2, "title": "Salt"})
    await _recipe(admin, show, "C", episode={"title": "salt"})
    channel = await _show(admin, "Joshua Weissman", kind="video_channel")
    await _recipe(admin, channel, "D", episode={"address": "https://youtube.com/watch?v=abc"})
    await _recipe(admin, channel, "E", episode={"address": "https://youtube.com/watch?v=abc"})
    rows = (
        await adb.execute(
            text("SELECT season, number, title FROM episodes ORDER BY url NULLS FIRST")
        )
    ).all()
    # The title given second fills in the first's blank.
    assert [tuple(r) for r in rows] == [(1, 2, "Salt"), (None, None, None)]


async def test_season_two_episode_two_is_another_episode(admin, adb) -> None:
    show = await _show(admin)
    await _recipe(admin, show, "A", episode={"season": 1, "number": 2})
    await _recipe(admin, show, "B", episode={"season": 2, "number": 2})
    await _recipe(admin, show, "C", episode={"number": 2})
    assert await adb.scalar(text("SELECT count(*) FROM episodes")) == 3


async def test_a_number_is_filled_in_unless_another_episode_has_it(admin, adb) -> None:
    show = await _show(admin, kind="podcast")
    await _recipe(admin, show, "A", episode={"title": "Bread"})
    await _recipe(admin, show, "B", episode={"number": 7, "title": "Bread"})
    assert await adb.scalar(text("SELECT number FROM episodes WHERE title = 'Bread'")) == 7
    await _recipe(admin, show, "C", episode={"title": "Cheese", "address": "https://pod.example/c"})
    # Found by its address, it can't take a number episode "Bread" has.
    made = await _recipe(
        admin, show, "D", episode={"number": 7, "address": "https://pod.example/c"}
    )
    assert made.status_code == 201, made.text
    assert await adb.scalar(text("SELECT number FROM episodes WHERE title = 'Cheese'")) is None


async def test_a_date_given_later_is_kept(admin, client) -> None:
    show = await _show(admin)
    await _recipe(admin, show, "A", episode={"number": 1})
    await _recipe(admin, show, "B", episode={"number": 1, "aired_on": "2018-10-11"})
    shown = (await client.get(f"/api/sources/{show}")).json()
    assert [e["aired_on"] for e in shown["episodes"]] == ["2018-10-11"]


async def test_an_episode_on_a_book_is_refused_even_unnamed(admin, adb) -> None:
    """A time or date with nothing naming the episode isn't dropped quietly."""
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    edition = await adb.scalar(
        text("INSERT INTO editions (source_id) VALUES (:b) RETURNING id"), {"b": book}
    )
    response = await _recipe(
        admin, book, "Cake", editions=[{"edition_id": str(edition)}], episode={"at": "1:00"}
    )
    assert response.status_code == 422


async def test_an_edit_moves_a_recipe_to_another_episode(admin) -> None:
    show = await _show(admin)
    made = await _recipe(admin, show, "Cake", episode={"number": 1, "at": "1:02:03"})
    assert (await _episode(admin, made.json()["id"]))["at"] == "1:02:03"
    response = await admin.put(
        f"/api/recipes/{made.json()['id']}",
        json={"title": "Cake", "episode": {"number": 4}, "ingredients": []},
    )
    assert response.status_code == 200, response.text
    assert (response.json()["episode"]["name"], response.json()["episode"]["at"]) == (
        "Episode 4",
        None,
    )


@pytest.mark.parametrize(
    ("kind", "episode", "says"),
    [
        ("tv_show", None, "which episode"),
        ("tv_show", {"season": 1}, "number in its season"),
        ("tv_show", {"at": "12:00"}, "which episode"),
        ("tv_show", {"number": 1, "at": "12:75"}, "minutes and seconds"),
        ("tv_show", {"number": 1, "at": "1:60:00"}, "minutes and seconds"),
        ("tv_show", {"number": -1}, "from 0"),
        ("video_channel", {"title": "Bagels"}, "video's address"),
        ("podcast", {"address": "not a web address"}, "address"),
    ],
)
async def test_a_bad_episode_is_refused(admin, kind, episode, says) -> None:
    show = await _show(admin, kind=kind)
    response = await _recipe(admin, show, "Cake", episode=episode)
    assert response.status_code == 422, response.text
    assert says in response.json()["detail"]


async def test_a_recipe_is_in_an_episode_and_only_an_episode(admin) -> None:
    show = await _show(admin)
    both = await _recipe(admin, show, "Cake", episode={"number": 1}, issue="May 2024")
    assert both.status_code == 422
    assert "one place" in both.json()["detail"]


async def test_only_a_show_has_episodes(admin, adb) -> None:
    site = (await admin.post("/api/sources/websites", json={"address": "example.com"})).json()
    magazine = (
        await admin.post("/api/sources/periodicals", json={"kind": "magazine", "title": "Saveur"})
    ).json()
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    for source in (site["id"], magazine["id"], book):
        response = await _recipe(admin, source, "Cake", episode={"number": 1})
        assert response.status_code == 422
        assert "Only a TV show, podcast or video channel" in response.json()["detail"]


async def test_a_shows_recipe_is_found_by_search(admin, adb, client) -> None:
    show = await _show(admin)
    await _recipe(admin, show, "Rhubarb Cake", episode={"number": 3})
    rhubarb = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Rhubarb'"))
    found = (await client.get("/api/search", params={"ingredient": [str(rhubarb)]})).json()
    assert [(r["title"], r["source_title"]) for r in found["recipes"]] == [
        ("Rhubarb Cake", "Salt Fat Acid Heat")
    ]


# What the database refuses


async def test_an_episode_belongs_to_its_own_source(admin, adb) -> None:
    """The composite key keeps a location in its own source's episode."""
    a = await _show(admin, "A")
    b = await _show(admin, "B")
    made = await _recipe(admin, a, "Cake", episode={"number": 1})
    other = await adb.scalar(
        text("INSERT INTO episodes (source_id, number) VALUES (:s, 1) RETURNING id"), {"s": b}
    )
    with pytest.raises(Exception, match="fk_recipe_locations_source_id_episode_id_episodes"):
        async with adb.begin_nested():
            await adb.execute(
                text("UPDATE recipe_locations SET episode_id = :e WHERE recipe_id = :r"),
                {"e": other, "r": uuid.UUID(made.json()["id"])},
            )


@pytest.mark.parametrize(
    ("columns", "values", "refused_by"),
    [
        ("source_id", ":s", "ck_episodes_named"),
        ("source_id, season, title", ":s, 1, 'Salt'", "ck_episodes_season_needs_number"),
        ("source_id, number", ":s, -1", "ck_episodes_numbers_not_negative"),
        ("source_id, title", ":s, ''", "ck_episodes_title_not_empty"),
        ("source_id, season, number", ":s, 1, 1", "uq_episodes_source_id_season_number"),
        ("source_id, number", ":s, 1", "uq_episodes_source_id_season_number"),
        ("source_id, url", ":s, 'https://example.com/v'", "uq_episodes_source_id_url"),
    ],
)
async def test_the_database_refuses_a_bad_episode(admin, adb, columns, values, refused_by) -> None:
    show = await _show(admin)
    for already in (
        "(source_id, season, number) VALUES (:s, 1, 1)",
        "(source_id, number) VALUES (:s, 1)",
        "(source_id, url) VALUES (:s, 'https://example.com/v')",
    ):
        await adb.execute(text(f"INSERT INTO episodes {already}"), {"s": show})
    with pytest.raises(Exception, match=refused_by):
        async with adb.begin_nested():
            await adb.execute(
                text(f"INSERT INTO episodes ({columns}) VALUES ({values})"), {"s": show}
            )


async def test_a_time_needs_an_episode(admin, adb) -> None:
    source = (
        await admin.post("/api/sources/periodicals", json={"kind": "magazine", "title": "Saveur"})
    ).json()["id"]
    made = await _recipe(admin, source, "Cake", issue="May 2024")
    with pytest.raises(Exception, match="ck_recipe_locations_time_needs_an_episode"):
        async with adb.begin_nested():
            await adb.execute(
                text("UPDATE recipe_locations SET at_seconds = 60 WHERE recipe_id = :r"),
                {"r": uuid.UUID(made.json()["id"])},
            )
