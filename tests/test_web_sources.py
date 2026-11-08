"""Websites as sources, and recipes on their pages."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in
from openlarder import web

E = uuid.uuid4()


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET is_admin = true"))
    return client


async def _site(client, address="https://www.SmittenKitchen.com/", **more):
    response = await client.post("/api/sources/websites", json={"address": address, **more})
    assert response.status_code == 200, response.text
    return response.json()


async def _web_recipe(client, site, title, address, ingredients=("Rhubarb",)):
    return await client.post(
        f"/api/sources/{site}/recipes",
        json={"title": title, "web_address": address, "ingredients": list(ingredients)},
    )


# Addresses


@pytest.mark.parametrize(
    "raw, url, host",
    [
        (
            " https://www.SmittenKitchen.com/2024/04/rhubarb-cake/#recipe ",
            "https://www.smittenkitchen.com/2024/04/rhubarb-cake/",
            "smittenkitchen.com",
        ),
        ("HTTP://example.com", "http://example.com/", "example.com"),
        (
            "https://cooking.nytimes.com/recipes/1?x=1",
            "https://cooking.nytimes.com/recipes/1?x=1",
            "cooking.nytimes.com",
        ),
    ],
)
def test_an_address_is_tidied_and_its_site_found(raw, url, host) -> None:
    assert web.page(raw) == (url, host)


@pytest.mark.parametrize(
    "raw", ["smittenkitchen.com/rhubarb", "ftp://example.com/x", "javascript:alert(1)", "https://"]
)
def test_an_address_must_be_a_web_page(raw) -> None:
    with pytest.raises(web.BadAddress):
        web.page(raw)


def test_a_site_is_found_from_a_host_or_an_address() -> None:
    assert web.site("WWW.Example.com") == "example.com"
    assert web.site("https://www.example.com/a/b") == "example.com"
    with pytest.raises(web.BadAddress):
        web.site("not a site")


# Adding a website


async def test_a_website_is_added_once_per_site(admin, client) -> None:
    first = await _site(admin, name=" Smitten  Kitchen ")
    again = await _site(admin, "smittenkitchen.com")
    assert (first["existing"], again) == (False, {"id": first["id"], "existing": True})
    site = (await client.get(f"/api/sources/{first['id']}")).json()
    assert (site["kind"], site["host"], site["title"], site["paywalled"]) == (
        "website",
        "smittenkitchen.com",
        "Smitten Kitchen",
        False,
    )
    assert site["editions"] == []
    listed = (await client.get("/api/sources")).json()
    assert [(s["kind"], s["host"]) for s in listed] == [("website", "smittenkitchen.com")]


async def test_a_website_is_named_by_its_host_until_named(admin, client) -> None:
    added = await _site(admin, "https://cooking.nytimes.com/recipes/1", paywalled=True)
    site = (await client.get(f"/api/sources/{added['id']}")).json()
    assert (site["title"], site["paywalled"]) == ("cooking.nytimes.com", True)


async def test_a_bad_website_address_is_refused(admin) -> None:
    response = await admin.post("/api/sources/websites", json={"address": "nowhere"})
    assert response.status_code == 422


async def test_only_admins_add_websites(admin, adb) -> None:
    await adb.execute(text("UPDATE users SET is_admin = false"))
    response = await admin.post("/api/sources/websites", json={"address": "example.com"})
    assert response.status_code == 403


# Recipes on a website


async def test_a_recipe_is_on_a_page_of_its_site(admin, client) -> None:
    site = (await _site(admin))["id"]
    response = await _web_recipe(
        admin, site, "Rhubarb Cake", "https://smittenkitchen.com/2024/04/rhubarb-cake/#jump"
    )
    assert response.status_code == 201, response.text
    recipe = (await client.get(f"/api/recipes/{response.json()['id']}")).json()
    assert recipe["source"] == {"id": site, "title": "smittenkitchen.com", "kind": "website"}
    assert recipe["web_address"] == "https://smittenkitchen.com/2024/04/rhubarb-cake/"
    assert recipe["pages"] == []
    # Its ingredients are matched like any recipe's.
    assert recipe["lines"][0]["options"][0]["ingredient"]["name"] == "Rhubarb"


async def test_recipes_can_share_a_page(admin, adb) -> None:
    site = (await _site(admin))["id"]
    page = "https://smittenkitchen.com/three-dressings/"
    for title in ("Lemon Dressing", "Herb Dressing"):
        assert (await _web_recipe(admin, site, title, page)).status_code == 201
    assert await adb.scalar(text("SELECT count(*) FROM web_pages")) == 1
    assert await adb.scalar(text("SELECT count(*) FROM recipe_locations")) == 2


async def test_an_edit_moves_a_recipe_to_another_page(admin, client) -> None:
    site = (await _site(admin))["id"]
    made = await _web_recipe(admin, site, "Cake", "https://smittenkitchen.com/a/")
    recipe = made.json()["id"]
    response = await admin.put(
        f"/api/recipes/{recipe}",
        json={"title": "Cake", "web_address": "https://smittenkitchen.com/b/", "ingredients": []},
    )
    assert response.status_code == 200, response.text
    assert response.json()["web_address"] == "https://smittenkitchen.com/b/"


@pytest.mark.parametrize(
    "body, reason",
    [
        ({"web_address": "https://example.com/cake/"}, "isn't on smittenkitchen.com"),
        ({}, "web address"),
        ({"web_address": "smittenkitchen.com/cake"}, "http"),
    ],
)
async def test_a_websites_recipe_needs_an_address_on_it(admin, body, reason) -> None:
    site = (await _site(admin))["id"]
    response = await admin.post(
        f"/api/sources/{site}/recipes", json={"title": "Cake", "ingredients": [], **body}
    )
    assert response.status_code == 422
    assert reason in response.json()["detail"]


async def test_a_book_is_in_editions_not_on_pages(admin, adb) -> None:
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    await adb.execute(
        text("INSERT INTO editions (id, source_id) VALUES (:id, :b)"), {"id": E, "b": book}
    )
    for body, reason in [
        ({"web_address": "https://example.com/cake/"}, "editions"),
        ({}, "edition"),
        (
            {"editions": [{"edition_id": str(E)}], "web_address": "https://example.com/cake/"},
            "not both",
        ),
    ]:
        response = await admin.post(
            f"/api/sources/{book}/recipes", json={"title": "Cake", "ingredients": [], **body}
        )
        assert response.status_code == 422, body
        assert reason in response.json()["detail"], body


async def test_a_websites_recipe_is_found_by_search(admin, adb, client) -> None:
    site = (await _site(admin))["id"]
    await _web_recipe(admin, site, "Rhubarb Cake", "https://smittenkitchen.com/cake/")
    rhubarb = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Rhubarb'"))
    found = (await client.get("/api/search", params={"ingredient": [str(rhubarb)]})).json()
    assert [(r["title"], r["source_title"], r["pages"]) for r in found["recipes"]] == [
        ("Rhubarb Cake", "smittenkitchen.com", [])
    ]


async def test_a_website_can_be_marked_a_subscription_site(admin, client, adb) -> None:
    site = (await _site(admin, name="NYT Cooking"))["id"]
    response = await admin.put(
        f"/api/sources/{site}", json={"title": "NYT Cooking", "paywalled": True}
    )
    assert response.status_code == 200, response.text
    assert (await client.get(f"/api/sources/{site}")).json()["paywalled"] is True
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    refused = await admin.put(
        f"/api/sources/{book}", json={"title": "Pink Cake", "paywalled": True}
    )
    assert refused.status_code == 422


async def test_a_website_doesnt_link_to_open_library(admin) -> None:
    site = (await _site(admin))["id"]
    response = await admin.post(
        f"/api/sources/{site}/open-library/preview", json={"reference": "9780393541113"}
    )
    assert response.status_code == 409


# Who writes it


async def test_a_website_credits_who_writes_it(admin, client) -> None:
    site = (
        await _site(admin, name="Smitten Kitchen", authors=["Deb Perelman", " Deb  Perelman "])
    )["id"]
    shown = (await client.get(f"/api/sources/{site}")).json()
    assert [(c["credited_as"], c["role"]) for c in shown["credits"]] == [("Deb Perelman", "author")]
    author = (await client.get(f"/api/authors/{shown['credits'][0]['author_id']}")).json()
    assert [(s["title"], s["kind"], s["host"]) for s in author["sources"]] == [
        ("Smitten Kitchen", "website", "smittenkitchen.com")
    ]


async def test_a_websites_author_is_the_same_as_her_books(admin, client) -> None:
    book = await admin.post(
        "/api/sources/manual",
        json={"title": "Smitten Kitchen Every Day", "authors": ["Deb Perelman"]},
    )
    site = (await _site(admin, authors=["Deb Perelman"]))["id"]
    shown = (await client.get(f"/api/sources/{site}")).json()
    deb = shown["credits"][0]["author_id"]
    page = (await client.get(f"/api/authors/{deb}")).json()
    assert sorted(s["kind"] for s in page["sources"]) == ["book", "website"]
    assert book.status_code == 200


async def test_a_websites_credits_are_edited_like_a_books(admin, client) -> None:
    site = (await _site(admin, name="Smitten Kitchen"))["id"]
    response = await admin.put(
        f"/api/sources/{site}",
        json={"title": "Smitten Kitchen", "credits": [{"name": "Deb Perelman", "role": "author"}]},
    )
    assert response.status_code == 200, response.text
    shown = (await client.get(f"/api/sources/{site}")).json()
    assert [c["credited_as"] for c in shown["credits"]] == ["Deb Perelman"]
