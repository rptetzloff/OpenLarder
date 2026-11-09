"""A source's page: what its recipe list says about each recipe."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in

NEW, OLD = uuid.uuid4(), uuid.uuid4()


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET is_admin = true"))
    return client


@pytest.fixture
async def book(adb):
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Biscuits') RETURNING id"))
    await adb.execute(
        text(
            "INSERT INTO editions (id, source_id, published_year) VALUES"
            " (:new, :b, 2020), (:old, :b, 2014)"
        ),
        {"new": NEW, "old": OLD, "b": book},
    )
    return book


async def _add(client, book, title, places, ingredients):
    response = await client.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": title,
            "editions": [{"edition_id": str(e), "page": p} for e, p in places],
            "ingredients": ingredients,
        },
    )
    assert response.status_code == 201, response.text


async def test_each_recipe_says_its_pages_lines_and_whether_its_a_component(
    admin, book, client
) -> None:
    await _add(admin, book, "Biscuit Blend", [(NEW, "14"), (OLD, "12")], ["Rice flour", "Starch"])
    await _add(
        admin,
        book,
        "Cheddar Biscuits",
        [(NEW, None)],
        ["Biscuit Blend (p. 14)", "Cheddar", "Butter", "Egg", "Milk"],
    )
    shown = (await client.get(f"/api/sources/{book}")).json()
    recipes = {r["title"]: r for r in shown["recipes"]}
    blend, biscuits = recipes["Biscuit Blend"], recipes["Cheddar Biscuits"]
    assert {(p["edition_id"], p["page"]) for p in blend["editions"]} == {
        (str(NEW), "14"),
        (str(OLD), "12"),
    }
    assert [(p["edition_id"], p["page"]) for p in biscuits["editions"]] == [(str(NEW), None)]
    assert (biscuits["lines"], biscuits["line_count"]) == (
        ["Biscuit Blend (p. 14)", "Cheddar", "Butter"],
        5,
    )
    assert (blend["lines"], blend["line_count"]) == (["Rice flour", "Starch"], 2)
    assert (blend["component"], biscuits["component"]) == (True, False)
