"""Social media accounts and products' packaging as sources."""

import pytest
from sqlalchemy import text

from fake_broker import _sign_in


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET is_admin = true"))
    return client


async def _named(client, kind, title, **more):
    response = await client.post(f"/api/sources/{kind}", json={"title": title, **more})
    assert response.status_code == 200, response.text
    return response.json()


async def _recipe(client, source, title, ingredients=("Oats",), **where):
    return await client.post(
        f"/api/sources/{source}/recipes",
        json={"title": title, "ingredients": list(ingredients), **where},
    )


# Adding one


@pytest.mark.parametrize("kind", ["social", "packaging"])
async def test_one_is_added_once_by_name(admin, client, kind) -> None:
    first = await _named(admin, kind, "  Half Baked  Harvest ", authors=["Tieghan Gerard"])
    again = await _named(admin, kind, "half baked harvest")
    assert (first["existing"], again) == (False, {"id": first["id"], "existing": True})
    shown = (await client.get(f"/api/sources/{first['id']}")).json()
    assert (shown["kind"], shown["title"]) == (kind, "Half Baked Harvest")
    assert [c["credited_as"] for c in shown["credits"]] == ["Tieghan Gerard"]


async def test_an_account_and_a_product_of_one_name_are_two_sources(admin) -> None:
    assert (await _named(admin, "social", "Oats"))["id"] != (
        await _named(admin, "packaging", "Oats")
    )["id"]


@pytest.mark.parametrize("kind", ["social", "packaging"])
async def test_a_blank_name_is_refused(admin, kind) -> None:
    assert (await admin.post(f"/api/sources/{kind}", json={"title": " "})).status_code == 422


@pytest.mark.parametrize("kind", ["social", "packaging"])
async def test_only_admins_add_them(admin, adb, kind) -> None:
    await adb.execute(text("UPDATE users SET is_admin = false"))
    assert (await admin.post(f"/api/sources/{kind}", json={"title": "X"})).status_code == 403


# Social media posts


async def test_a_post_is_on_any_site_and_archived(admin, client, ia) -> None:
    post = "https://www.instagram.com/p/abc123/"
    ia.statuses = [{"status": "success", "timestamp": "20261108153000", "original_url": post}]
    account = (await _named(admin, "social", "Half Baked Harvest (Instagram)"))["id"]
    made = await _recipe(
        admin, account, "Crispy Gnocchi", web_address="https://www.instagram.com/p/abc123/"
    )
    assert made.status_code == 201, made.text
    recipe = (await client.get(f"/api/recipes/{made.json()['id']}")).json()
    assert recipe["source"]["kind"] == "social"
    assert recipe["web_address"] == "https://www.instagram.com/p/abc123/"
    assert recipe["web_page"]["archive_url"] == (
        "https://web.archive.org/web/20261108153000/https://www.instagram.com/p/abc123/"
    )
    elsewhere = await _recipe(admin, account, "Soup", web_address="https://threads.net/@hbh/post/9")
    assert elsewhere.status_code == 201, elsewhere.text


async def test_a_post_needs_its_address(admin) -> None:
    account = (await _named(admin, "social", "HBH"))["id"]
    response = await _recipe(admin, account, "Gnocchi")
    assert response.status_code == 422
    assert "web address" in response.json()["detail"]


async def test_a_post_already_another_sources_is_refused(admin) -> None:
    one = (await _named(admin, "social", "One"))["id"]
    two = (await _named(admin, "social", "Two"))["id"]
    post = "https://www.instagram.com/p/shared/"
    assert (await _recipe(admin, one, "A", web_address=post)).status_code == 201
    response = await _recipe(admin, two, "B", web_address=post)
    assert response.status_code == 422
    assert "already one of One's" in response.json()["detail"]
    # Within its own account, a post can hold several recipes.
    assert (await _recipe(admin, one, "C", web_address=post)).status_code == 201


async def test_a_websites_page_is_refused_to_an_account(admin) -> None:
    site = (await admin.post("/api/sources/websites", json={"address": "example.com"})).json()
    await _recipe(admin, site["id"], "Cake", web_address="https://example.com/cake")
    account = (await _named(admin, "social", "Someone"))["id"]
    response = await _recipe(admin, account, "Cake", web_address="https://example.com/cake")
    assert response.status_code == 422
    assert "already one of example.com's" in response.json()["detail"]


# Packaging


async def test_a_recipe_on_packaging_has_no_place(admin, client, adb) -> None:
    product = (await _named(admin, "packaging", "Quaker Old Fashioned Oats"))["id"]
    made = await _recipe(admin, product, "Vanishing Oatmeal Raisin Cookies")
    assert made.status_code == 201, made.text
    recipe = (await client.get(f"/api/recipes/{made.json()['id']}")).json()
    assert (recipe["source"]["kind"], recipe["pages"], recipe["web_address"]) == (
        "packaging",
        [],
        None,
    )
    assert (recipe["issue"], recipe["episode"]) == (None, None)
    assert await adb.scalar(text("SELECT count(*) FROM recipe_locations")) == 0
    shown = (await client.get(f"/api/sources/{product}")).json()
    assert [r["title"] for r in shown["recipes"]] == ["Vanishing Oatmeal Raisin Cookies"]


@pytest.mark.parametrize(
    ("where", "says"),
    [
        ({"web_address": "https://example.com/cookies"}, "is just in it"),
        ({"issue": "May 2024"}, "Only a magazine or newspaper"),
        ({"episode": {"number": 1}}, "Only a TV show"),
    ],
)
async def test_a_recipe_on_packaging_takes_no_place(admin, adb, where, says) -> None:
    product = (await _named(admin, "packaging", "Oats"))["id"]
    response = await _recipe(admin, product, "Cookies", **where)
    assert response.status_code == 422
    assert says in response.json()["detail"]


async def test_a_recipe_on_packaging_takes_no_edition(admin, adb) -> None:
    product = (await _named(admin, "packaging", "Oats"))["id"]
    # Even an edition of its own: packaging has none, but the rule is the
    # message, not just the composite key.
    edition = await adb.scalar(
        text("INSERT INTO editions (source_id) VALUES (:s) RETURNING id"), {"s": product}
    )
    response = await _recipe(admin, product, "Cookies", editions=[{"edition_id": str(edition)}])
    assert response.status_code == 422
    assert "is just in it" in response.json()["detail"]
