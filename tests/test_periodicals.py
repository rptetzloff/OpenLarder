"""Magazines and newspapers as sources, and recipes in their issues."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET role = 'admin'"))
    return client


async def _periodical(client, title="Bon Appétit", kind="magazine", **more):
    response = await client.post(
        "/api/sources/periodicals", json={"kind": kind, "title": title, **more}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _recipe(client, source, title, ingredients=("Rhubarb",), **where):
    return await client.post(
        f"/api/sources/{source}/recipes",
        json={"title": title, "ingredients": list(ingredients), **where},
    )


# Adding one


async def test_a_magazine_is_added_once_by_name(admin, client) -> None:
    first = await _periodical(admin, "  Bon  Appétit ", authors=["Dawn Perry"])
    again = await _periodical(admin, "bon appétit")
    assert (first["existing"], again) == (False, {"id": first["id"], "existing": True})
    shown = (await client.get(f"/api/sources/{first['id']}")).json()
    assert (shown["kind"], shown["title"], shown["issues"], shown["editions"]) == (
        "magazine",
        "Bon Appétit",
        [],
        [],
    )
    assert [c["credited_as"] for c in shown["credits"]] == ["Dawn Perry"]


async def test_a_newspaper_of_the_same_name_is_another_source(admin) -> None:
    magazine = await _periodical(admin, "The Times")
    paper = await _periodical(admin, "The Times", kind="newspaper")
    assert magazine["id"] != paper["id"]


@pytest.mark.parametrize(
    "body", [{"kind": "magazine", "title": "  "}, {"kind": "zine", "title": "Lucky Peach"}]
)
async def test_a_bad_periodical_is_refused(admin, body) -> None:
    assert (await admin.post("/api/sources/periodicals", json=body)).status_code == 422


async def test_only_admins_add_periodicals(admin, adb) -> None:
    await adb.execute(text("UPDATE users SET role = 'user'"))
    response = await admin.post("/api/sources/periodicals", json={"kind": "magazine", "title": "X"})
    assert response.status_code == 403


# Recipes in issues


async def test_a_recipe_is_in_an_issue_at_a_page(admin, client) -> None:
    source = (await _periodical(admin))["id"]
    made = await _recipe(admin, source, "Rhubarb Cake", issue=" May  2024 ", issue_page=" 42 ")
    assert made.status_code == 201, made.text
    recipe = (await client.get(f"/api/recipes/{made.json()['id']}")).json()
    assert recipe["source"]["kind"] == "magazine"
    issue = recipe["issue"]
    assert (issue["label"], issue["published_on"], issue["page"]) == ("May 2024", None, "42")
    assert (recipe["pages"], recipe["web_address"]) == ([], None)
    shown = (await client.get(f"/api/sources/{source}")).json()
    assert [i["label"] for i in shown["issues"]] == ["May 2024"]
    assert [(r["title"], r["issue"], r["pages"]) for r in shown["recipes"]] == [
        ("Rhubarb Cake", "May 2024", ["42"])
    ]


async def test_recipes_share_an_issue_whatever_the_case(admin, adb) -> None:
    source = (await _periodical(admin))["id"]
    await _recipe(admin, source, "Cake", issue="May 2024")
    await _recipe(admin, source, "Fool", issue="may 2024", issue_page="12")
    assert await adb.scalar(text("SELECT count(*) FROM issues")) == 1


async def test_a_newspaper_issue_is_its_date(admin, client) -> None:
    source = (await _periodical(admin, "The New York Times", kind="newspaper"))["id"]
    made = await _recipe(admin, source, "Plum Torte", issue_date="2024-09-18", issue_page="D3")
    issue = (await client.get(f"/api/recipes/{made.json()['id']}")).json()["issue"]
    assert (issue["label"], issue["published_on"], issue["page"]) == (
        "2024-09-18",
        "2024-09-18",
        "D3",
    )


async def test_a_date_given_later_is_kept(admin, client) -> None:
    source = (await _periodical(admin))["id"]
    await _recipe(admin, source, "Cake", issue="Holiday 2023")
    made = await _recipe(admin, source, "Cookies", issue="Holiday 2023", issue_date="2023-12-01")
    shown = (await client.get(f"/api/sources/{source}")).json()
    assert shown["issues"][0]["published_on"] == "2023-12-01"
    assert made.status_code == 201


async def test_an_edit_moves_a_recipe_to_another_issue(admin, client) -> None:
    source = (await _periodical(admin))["id"]
    made = await _recipe(admin, source, "Cake", issue="May 2024", issue_page="42")
    recipe = made.json()["id"]
    response = await admin.put(
        f"/api/recipes/{recipe}",
        json={"title": "Cake", "issue": "June 2024", "issue_page": "7", "ingredients": []},
    )
    assert response.status_code == 200, response.text
    assert (response.json()["issue"]["label"], response.json()["issue"]["page"]) == (
        "June 2024",
        "7",
    )


async def test_a_periodicals_recipe_needs_an_issue_and_only_an_issue(admin, adb) -> None:
    source = (await _periodical(admin))["id"]
    missing = await _recipe(admin, source, "Cake", issue_page="42")
    assert missing.status_code == 422
    assert "issue" in missing.json()["detail"]
    both = await _recipe(admin, source, "Cake", issue="May", web_address="https://example.com/")
    assert both.status_code == 422
    assert "one place" in both.json()["detail"]


async def test_only_a_periodical_has_issues(admin, adb) -> None:
    site = (await admin.post("/api/sources/websites", json={"address": "example.com"})).json()
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    for source in (site["id"], book):
        response = await _recipe(admin, source, "Cake", issue="May 2024")
        assert response.status_code == 422
        assert "Only a magazine or newspaper" in response.json()["detail"]


async def test_a_periodicals_recipe_is_found_by_search(admin, adb, client) -> None:
    source = (await _periodical(admin))["id"]
    await _recipe(admin, source, "Rhubarb Cake", issue="May 2024", issue_page="42")
    rhubarb = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Rhubarb'"))
    found = (await client.get("/api/search", params={"ingredient": [str(rhubarb)]})).json()
    assert [(r["title"], r["source_title"], r["pages"]) for r in found["recipes"]] == [
        ("Rhubarb Cake", "Bon Appétit", ["42"])
    ]


async def test_an_issue_belongs_to_its_own_source(admin, adb) -> None:
    """The composite key keeps a location in its own source's issue."""
    a = (await _periodical(admin, "Saveur"))["id"]
    b = (await _periodical(admin, "Food & Wine"))["id"]
    made = await _recipe(admin, a, "Cake", issue="May 2024")
    other_issue = await adb.scalar(
        text("INSERT INTO issues (source_id, label) VALUES (:s, 'June') RETURNING id"), {"s": b}
    )
    with pytest.raises(Exception, match="fk_recipe_locations_source_id_issue_id_issues"):
        async with adb.begin_nested():
            await adb.execute(
                text("UPDATE recipe_locations SET issue_id = :i WHERE recipe_id = :r"),
                {"i": other_issue, "r": uuid.UUID(made.json()["id"])},
            )
