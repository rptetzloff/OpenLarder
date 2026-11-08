"""Flagged recipes: who sees which flags, and dealing with them."""

import pytest
from sqlalchemy import text

from fake_broker import _sign_in


async def _user_id(adb, subject):
    return await adb.scalar(text("SELECT id FROM users WHERE subject = :s"), {"s": subject})


@pytest.fixture
async def setup(client, broker, adb):
    """Ann (admin) and Bo each add a recipe; each recipe has flags."""
    broker.subject = "bo"
    await _sign_in(client, broker)
    broker.subject = "ann"
    await _sign_in(client, broker)  # the client is now Ann's
    ann, bo = await _user_id(adb, "ann"), await _user_id(adb, "bo")
    await adb.execute(text("UPDATE users SET is_admin = (subject = 'ann')"))
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    recipes = {}
    for owner, title in ((ann, "Ann's Cake"), (bo, "Bo's Bread")):
        recipes[title] = await adb.scalar(
            text(
                "INSERT INTO recipes (source_id, title, created_by)"
                " VALUES (:w, :t, :o) RETURNING id"
            ),
            {"w": work, "t": title, "o": owner},
        )
    flags = {}
    for title, kind in (
        ("Ann's Cake", "no_ingredients"),
        ("Bo's Bread", "no_page"),
        ("Bo's Bread", "duplicate_title"),
    ):
        flags[(title, kind)] = await adb.scalar(
            text("INSERT INTO recipe_flags (recipe_id, kind) VALUES (:r, :k) RETURNING id"),
            {"r": recipes[title], "k": kind},
        )
    return {"recipes": recipes, "flags": flags}


async def _as(client, broker, subject):
    broker.subject = subject
    await _sign_in(client, broker)


async def test_an_admin_sees_every_flag_with_counts(client, setup) -> None:
    page = (await client.get("/api/flags", params={"scope": "all"})).json()
    assert page["total"] == 3
    assert page["open_by_kind"] == {"no_ingredients": 1, "no_page": 1, "duplicate_title": 1}
    assert [f["recipe"]["title"] for f in page["flags"]] == [
        "Ann's Cake",
        "Bo's Bread",
        "Bo's Bread",
    ]


async def test_each_person_sees_flags_on_their_own_recipes(client, broker, setup) -> None:
    await _as(client, broker, "bo")
    mine = (await client.get("/api/flags")).json()
    assert {f["recipe"]["title"] for f in mine["flags"]} == {"Bo's Bread"}
    assert mine["open_by_kind"] == {"no_page": 1, "duplicate_title": 1}
    assert (await client.get("/api/flags", params={"scope": "all"})).status_code == 403


async def test_flags_filter_by_kind(client, setup) -> None:
    page = (await client.get("/api/flags", params={"scope": "all", "kind": "no_page"})).json()
    assert [f["kind"] for f in page["flags"]] == ["no_page"]


async def test_the_owner_can_mark_a_flag_fixed(client, broker, setup, adb) -> None:
    await _as(client, broker, "bo")
    flag = setup["flags"][("Bo's Bread", "no_page")]
    response = await client.post(f"/api/flags/{flag}/resolve", json={"resolution": "fixed"})
    assert response.status_code == 200
    assert response.json()["resolution"] == "fixed" and response.json()["resolved_at"]
    open_now = (await client.get("/api/flags")).json()
    assert [f["kind"] for f in open_now["flags"]] == ["duplicate_title"]
    dealt = (await client.get("/api/flags", params={"state": "dealt_with"})).json()
    assert [f["kind"] for f in dealt["flags"]] == ["no_page"]
    assert await adb.scalar(
        text("SELECT resolved_by FROM recipe_flags WHERE id = :f"), {"f": flag}
    ) == await _user_id(adb, "bo")


async def test_dismissing_needs_a_reason_which_is_kept(client, setup) -> None:
    flag = setup["flags"][("Ann's Cake", "no_ingredients")]
    bare = await client.post(
        f"/api/flags/{flag}/resolve", json={"resolution": "dismissed", "note": "  "}
    )
    assert bare.status_code == 422
    kept = await client.post(
        f"/api/flags/{flag}/resolve",
        json={"resolution": "dismissed", "note": "The book  lists none"},
    )
    assert (kept.json()["resolution"], kept.json()["note"]) == ("dismissed", "The book lists none")


async def test_a_flag_is_dealt_with_once(client, setup) -> None:
    flag = setup["flags"][("Ann's Cake", "no_ingredients")]
    await client.post(f"/api/flags/{flag}/resolve", json={"resolution": "fixed"})
    again = await client.post(f"/api/flags/{flag}/resolve", json={"resolution": "fixed"})
    assert again.status_code == 409


async def test_someone_else_cannot_deal_with_your_flags(client, broker, setup) -> None:
    await _as(client, broker, "bo")
    flag = setup["flags"][("Ann's Cake", "no_ingredients")]
    response = await client.post(f"/api/flags/{flag}/resolve", json={"resolution": "fixed"})
    assert response.status_code == 403


async def test_an_admin_can_deal_with_anyones(client, setup) -> None:
    flag = setup["flags"][("Bo's Bread", "no_page")]
    response = await client.post(f"/api/flags/{flag}/resolve", json={"resolution": "fixed"})
    assert response.status_code == 200


async def test_a_recipes_flags_show_only_to_who_may_deal_with_them(client, broker, setup) -> None:
    ann_recipe = setup["recipes"]["Ann's Cake"]
    assert len((await client.get(f"/api/recipes/{ann_recipe}/flags")).json()) == 1
    await _as(client, broker, "bo")
    assert (await client.get(f"/api/recipes/{ann_recipe}/flags")).json() == []
    bo_recipe = setup["recipes"]["Bo's Bread"]
    assert len((await client.get(f"/api/recipes/{bo_recipe}/flags")).json()) == 2


async def test_another_sites_page_cannot_resolve(client, setup) -> None:
    flag = setup["flags"][("Ann's Cake", "no_ingredients")]
    response = await client.post(
        f"/api/flags/{flag}/resolve",
        json={"resolution": "fixed"},
        headers={"Origin": "https://auth.openlarder.com"},
    )
    assert response.status_code == 403


async def test_flags_come_fifty_to_a_page(client, setup, adb) -> None:
    recipe = setup["recipes"]["Ann's Cake"]
    for _ in range(50):
        await adb.execute(
            text("INSERT INTO recipe_flags (recipe_id, kind) VALUES (:r, 'no_page')"), {"r": recipe}
        )
    first = (await client.get("/api/flags", params={"scope": "all"})).json()
    rest = (await client.get("/api/flags", params={"scope": "all", "offset": 50})).json()
    assert (len(first["flags"]), first["total"], len(rest["flags"])) == (50, 53, 3)


async def test_flags_need_a_session(client) -> None:
    assert (await client.get("/api/flags")).status_code == 401
