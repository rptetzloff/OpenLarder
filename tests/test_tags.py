"""Tags: the fixed list, tagging sources and recipes, and searching by tag."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in

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
    await adb.execute(text("UPDATE users SET role = 'admin'"))
    return client


async def _add(client, work, title):
    response = await client.post(
        f"/api/sources/{work}/recipes",
        json={"title": title, "editions": [{"edition_id": str(E), "page": "1"}]},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _tag(client, kind, name):
    return next(
        t["id"]
        for t in (await client.get("/api/tags")).json()
        if t["kind"] == kind and t["name"] == name
    )


async def test_the_starter_list_is_there_diet_first(client) -> None:
    tags = (await client.get("/api/tags")).json()
    kinds = list(dict.fromkeys(t["kind"] for t in tags))
    assert kinds == ["diet", "course", "cuisine", "technique"]
    assert {"Vegetarian", "Gluten-Free"} <= {t["name"] for t in tags if t["kind"] == "diet"}
    diets = [t["name"] for t in tags if t["kind"] == "diet"]
    assert diets == sorted(diets, key=str.lower)


async def test_only_an_admin_adds_a_tag_and_once(admin, adb) -> None:
    added = await admin.post("/api/tags", json={"kind": "cuisine", "name": "  Georgian "})
    assert added.status_code == 201
    assert added.json()["name"] == "Georgian"
    again = await admin.post("/api/tags", json={"kind": "cuisine", "name": "georgian"})
    assert again.status_code == 409
    blank = await admin.post("/api/tags", json={"kind": "cuisine", "name": " "})
    assert blank.status_code == 422
    await adb.execute(text("UPDATE users SET role = 'user'"))
    refused = await admin.post("/api/tags", json={"kind": "cuisine", "name": "Uzbek"})
    assert refused.status_code == 403


async def test_a_recipe_is_tagged_and_retagged(admin, client, work) -> None:
    cake = await _add(admin, work, "Rhubarb Cake")
    dessert = await _tag(client, "course", "Dessert")
    vegetarian = await _tag(client, "diet", "Vegetarian")
    tagged = await admin.put(f"/api/recipes/{cake}/tags", json={"tags": [dessert, vegetarian]})
    assert tagged.status_code == 200, tagged.text
    # Diet first.
    assert [t["name"] for t in tagged.json()] == ["Vegetarian", "Dessert"]
    shown = (await client.get(f"/api/recipes/{cake}")).json()["tags"]
    assert [(t["name"], t["from_source"]) for t in shown] == [
        ("Vegetarian", False),
        ("Dessert", False),
    ]
    # All of them, every time: one left out is taken off.
    await admin.put(f"/api/recipes/{cake}/tags", json={"tags": [dessert]})
    shown = (await client.get(f"/api/recipes/{cake}")).json()["tags"]
    assert [t["name"] for t in shown] == ["Dessert"]
    unknown = await admin.put(f"/api/recipes/{cake}/tags", json={"tags": [str(uuid.uuid4())]})
    assert unknown.status_code == 422


async def test_a_sources_tags_are_its_recipes_too(admin, client, work) -> None:
    cake = await _add(admin, work, "Rhubarb Cake")
    gluten_free = await _tag(client, "diet", "Gluten-Free")
    dessert = await _tag(client, "course", "Dessert")
    response = await admin.put(f"/api/sources/{work}/tags", json={"tags": [gluten_free]})
    assert [t["name"] for t in response.json()] == ["Gluten-Free"]
    assert [t["name"] for t in (await client.get(f"/api/sources/{work}")).json()["tags"]] == [
        "Gluten-Free"
    ]
    await admin.put(f"/api/recipes/{cake}/tags", json={"tags": [dessert, gluten_free]})
    shown = (await client.get(f"/api/recipes/{cake}")).json()["tags"]
    # Its own as well as its source's: shown once, as its own.
    assert [(t["name"], t["from_source"]) for t in shown] == [
        ("Gluten-Free", False),
        ("Dessert", False),
    ]
    await admin.put(f"/api/recipes/{cake}/tags", json={"tags": [dessert]})
    shown = (await client.get(f"/api/recipes/{cake}")).json()["tags"]
    assert [(t["name"], t["from_source"]) for t in shown] == [
        ("Gluten-Free", True),
        ("Dessert", False),
    ]


async def test_only_whoever_may_change_it_tags_it(admin, client, broker, work, adb) -> None:
    cake = await _add(admin, work, "Rhubarb Cake")
    dessert = await _tag(client, "course", "Dessert")
    await adb.execute(text("UPDATE users SET role = 'user'"))
    for path in (f"/api/recipes/{cake}/tags", f"/api/sources/{work}/tags"):
        assert (await admin.put(path, json={"tags": [dessert]})).status_code == 403


async def test_searching_by_tag_alone_or_with_a_title(admin, client, work, adb) -> None:
    cake = await _add(admin, work, "Rhubarb Cake")
    await _add(admin, work, "Rhubarb Pickle")
    other = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Free From') RETURNING id"))
    edition = await adb.scalar(
        text("INSERT INTO editions (source_id) VALUES (:w) RETURNING id"), {"w": other}
    )
    loaf = await admin.post(
        f"/api/sources/{other}/recipes",
        json={"title": "Rhubarb Loaf", "editions": [{"edition_id": str(edition)}]},
    )
    assert loaf.status_code == 201
    dessert = await _tag(client, "course", "Dessert")
    gluten_free = await _tag(client, "diet", "Gluten-Free")
    await admin.put(f"/api/recipes/{cake}/tags", json={"tags": [dessert, gluten_free]})
    await admin.put(f"/api/sources/{other}/tags", json={"tags": [gluten_free]})

    def titles(found):
        return sorted(r["title"] for r in found["recipes"])

    by_diet = (await client.get("/api/search", params={"tag": gluten_free})).json()
    assert titles(by_diet) == ["Rhubarb Cake", "Rhubarb Loaf"]
    assert by_diet["tags"] == [{"id": gluten_free, "name": "Gluten-Free"}]
    # Every tag asked for.
    both = (await client.get("/api/search", params={"tag": [gluten_free, dessert]})).json()
    assert titles(both) == ["Rhubarb Cake"]
    with_title = (await client.get("/api/search", params={"tag": gluten_free, "q": "loaf"})).json()
    assert titles(with_title) == ["Rhubarb Loaf"]
    gone = str(uuid.uuid4())
    missing = (await client.get("/api/search", params={"tag": gone})).json()
    assert (missing["recipes"], missing["missing_tags"]) == ([], [gone])
