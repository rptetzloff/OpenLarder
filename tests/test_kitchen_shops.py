"""Equipment's shop links (kitchen.py) and counting their clicks (routers/
go.py): the grocery links' tests over again (tests/test_grocery.py), for
the `kitchen` kind of shop. *Ray's equipment spec, 2026-11-15, Part 8.*"""

import importlib.util
import pathlib
from urllib.parse import unquote

import pytest
from sqlalchemy import text

from openlarder import shops

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/140.0"}
TEMPLATE = "https://partner.example/deeplink?murl={url}"


@pytest.fixture
async def kitchen(adb):
    """Amazon switched on with a tag, and a second shop added after it, as
    an administrator would on the Shops page."""
    await adb.execute(
        text(
            "UPDATE shops SET affiliate_id = 'openlarder-20', enabled = true"
            " WHERE kind = 'kitchen' AND key = 'amazon'"
        )
    )
    await adb.execute(
        text(
            "INSERT INTO shops (kind, key, label, builder, wrapper_template, product_template,"
            " enabled, position) VALUES ('kitchen', 'panhandle', 'Panhandle', 'wrapped', :w,"
            " 'https://panhandle.example/search?q={term}', true, 1)"
        ),
        {"w": TEMPLATE},
    )
    shops.reset()
    yield
    shops.reset()


async def _thing(adb, name: str) -> str:
    return str(await adb.scalar(text("SELECT id FROM equipment WHERE name = :n"), {"n": name}))


async def test_none_until_one_is_switched_on_with_its_setting(client, adb) -> None:
    """As it's seeded: there, off, and sending nobody anywhere."""
    shops.reset()
    oven = await _thing(adb, "Dutch oven")

    async def nothing() -> None:
        shops.reset()
        assert (await client.get("/api/kitchen-shops")).json() == []
        r = await client.get(f"/go/equipment/amazon/{oven}", headers=BROWSER)
        assert r.status_code == 404 and r.headers["cache-control"] == "no-store"

    await nothing()
    # With its tag and still off, which is how the migration leaves it
    # where the bookseller has one: nothing, until someone switches it on.
    await adb.execute(
        text("UPDATE shops SET affiliate_id = 'openlarder-20' WHERE kind = 'kitchen'")
    )
    await nothing()
    # On with no tag, it's not offered either: a link that earns nothing
    # isn't shown.
    await adb.execute(
        text("UPDATE shops SET affiliate_id = NULL, enabled = true WHERE kind = 'kitchen'")
    )
    await nothing()
    # Both, and it is.
    await adb.execute(
        text("UPDATE shops SET affiliate_id = 'openlarder-20' WHERE kind = 'kitchen'")
    )
    shops.reset()
    assert [k["key"] for k in (await client.get("/api/kitchen-shops")).json()] == ["amazon"]
    assert (await client.get(f"/go/equipment/amazon/{oven}", headers=BROWSER)).status_code == 302
    shops.reset()


async def test_the_shops_on_offer_in_their_order(client, kitchen) -> None:
    shown = (await client.get("/api/kitchen-shops")).json()
    assert [s["key"] for s in shown] == ["amazon", "panhandle"]
    assert shown[0]["label"] == "Amazon" and "Amazon Associate" in shown[0]["note"]
    # The grocers are their own list, and the kitchen shops aren't in it.
    assert (await client.get("/api/grocers")).json() == []


async def test_a_click_is_counted_and_sent_on(client, adb, kitchen) -> None:
    oven = await _thing(adb, "Dutch oven")
    r = await client.get(
        f"/go/equipment/amazon/{oven}", params={"from": "/recipes/abc"}, headers=BROWSER
    )
    assert r.status_code == 302 and r.headers["cache-control"] == "no-store"
    # A search of all of Amazon: no department, where a grocer's names
    # Amazon Fresh.
    assert r.headers["location"] == "https://www.amazon.com/s?k=Dutch+oven&tag=openlarder-20"
    r = await client.get(f"/go/equipment/panhandle/{oven}", headers=BROWSER)
    target = r.headers["location"]
    assert target.startswith("https://partner.example/deeplink?murl=")
    assert unquote(target.split("murl=")[1]) == "https://panhandle.example/search?q=Dutch+oven"
    clicks = (
        await adb.execute(
            text("SELECT shop, page, equipment_id::text FROM equipment_clicks ORDER BY clicked_at")
        )
    ).all()
    assert sorted(clicks) == [("amazon", "/recipes/abc", oven), ("panhandle", None, oven)]
    # A bot is sent on, uncounted.
    bot = await client.get(f"/go/equipment/amazon/{oven}", headers={"User-Agent": "Googlebot/2.1"})
    assert bot.status_code == 302
    assert await adb.scalar(text("SELECT count(*) FROM equipment_clicks")) == 2
    # No such shop, no such thing, and a grocer's key isn't a kitchen shop's.
    gone = "00000000-0000-0000-0000-000000000000"
    for path in (
        f"/go/equipment/kroger/{oven}",
        f"/go/equipment/amazon/{gone}",
        f"/go/equipment/instacart/{oven}",
    ):
        assert (await client.get(path, headers=BROWSER)).status_code == 404, path
    # Nor is a piece of equipment an ingredient: the grocers' address has
    # none of that id.
    assert (await client.get(f"/go/grocer/amazon/{oven}", headers=BROWSER)).status_code == 404
    assert await adb.scalar(text("SELECT count(*) FROM equipment_clicks")) == 2


async def test_the_shopping_term_is_searched_for(client, adb, kitchen) -> None:
    oven = await _thing(adb, "Dutch oven")
    await adb.execute(
        text("UPDATE equipment SET shopping_term = 'enameled dutch oven, 5 qt' WHERE id = :e"),
        {"e": oven},
    )
    r = await client.get(f"/go/equipment/panhandle/{oven}", headers=BROWSER)
    assert unquote(r.headers["location"].split("murl=")[1]) == (
        "https://panhandle.example/search?q=enameled+dutch+oven%2C+5+qt"
    )


async def test_a_thing_a_hidden_recipe_brought_has_no_link_for_anyone_else(
    people, client, adb, kitchen
) -> None:
    ann, ad = await people("ann"), await people("ad", admin=True)
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    made = await ann.post(
        f"/api/sources/{box}/recipes",
        json={"title": "Nana's", "ingredients": ["eggs"], "equipment": ["moonbeam press"]},
    )
    assert made.status_code == 201, made.text
    press = await _thing(adb, "Moonbeam press")
    path = f"/go/equipment/amazon/{press}"
    # The address would say its name to whoever followed it.
    assert (await client.get(path, headers=BROWSER)).status_code == 404
    assert (await ad.get(path, headers=BROWSER)).status_code == 404
    hers = await ann.get(path, headers=BROWSER)
    assert hers.headers["location"] == "https://www.amazon.com/s?k=Moonbeam+press&tag=openlarder-20"
    # Counted, and not named to an administrator who can't see it.
    page = (await ad.get("/api/admin/clicks")).json()
    assert page["equipment_clicks"] == 1 and page["equipment"] == []
    assert "Moonbeam" not in str(page)


async def test_admins_see_equipment_clicks(people, client, adb, kitchen) -> None:
    ad = await people("ad", role="admin")
    oven, wok = await _thing(adb, "Dutch oven"), await _thing(adb, "Wok")
    for path in (f"amazon/{oven}", f"amazon/{oven}", f"panhandle/{wok}"):
        await client.get(f"/go/equipment/{path}", headers=BROWSER)
    page = (await ad.get("/api/admin/clicks")).json()
    assert page["equipment_clicks"] == 3
    assert [(s["label"], s["clicks"]) for s in page["kitchen_shops"]] == [
        ("Amazon", 2),
        ("Panhandle", 1),
    ]
    assert page["equipment"] == [
        {"equipment_id": oven, "name": "Dutch oven", "clicks": 2},
        {"equipment_id": wok, "name": "Wok", "clicks": 1},
    ]
    # They aren't grocery clicks, nor the books'.
    assert (page["grocery_clicks"], page["clicks"]) == (0, 0)
    # And on the Shops page, beside each shop.
    groups = {g["kind"]: g for g in (await ad.get("/api/admin/shops")).json()}
    assert [(s["key"], s["clicks"]) for s in groups["kitchen"]["shops"]] == [
        ("amazon", 2),
        ("panhandle", 1),
    ]
    assert (
        await (await people("mo", role="moderator")).get("/api/admin/clicks")
    ).status_code == 403


async def test_an_administrator_adds_a_kitchen_shop(people, client, adb) -> None:
    ann = await people("ann", admin=True)
    added = await ann.post(
        "/api/admin/shops",
        json={
            "key": "corner-shop",
            "kind": "kitchen",
            "label": "The Corner Shop",
            "builder": "template",
            "product_template": "https://corner.example/kit?q={term}",
            "enabled": True,
        },
    )
    assert added.status_code == 200, added.text
    oven = await _thing(adb, "Dutch oven")
    r = await client.get(f"/go/equipment/corner-shop/{oven}", headers=BROWSER)
    assert r.headers["location"] == "https://corner.example/kit?q=Dutch+oven"
    # Its address asks for a term, not a book's ISBN.
    wrong = await ann.post(
        "/api/admin/shops",
        json={
            "key": "other-shop",
            "kind": "kitchen",
            "label": "Other",
            "builder": "template",
            "product_template": "https://other.example/?isbn={isbn13}",
        },
    )
    assert wrong.status_code == 422, wrong.text
    # "Test link" tries it with a piece of equipment.
    tried = await ann.post(
        "/api/admin/shops/test",
        json={
            "key": "x",
            "kind": "kitchen",
            "label": "X",
            "builder": "template",
            "product_template": "https://x.example/?q={term}",
        },
    )
    assert tried.status_code == 200, tried.text
    assert tried.json()["url"] == "https://x.example/?q=Dutch+oven"
    assert tried.json()["sample"] == "the equipment “Dutch oven”"
    shops.reset()


async def test_the_migration_gives_amazon_the_booksellers_tag_switched_off(adb) -> None:
    """Seeded where the tests' database was made, the bookseller had no
    tag. With one, the kitchen shop starts with it, and off."""
    path = pathlib.Path(__file__).parent.parent / "migrations/versions/0086_kitchen_shops.py"
    spec = importlib.util.spec_from_file_location("migration_0086", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    seeded = text(
        "SELECT affiliate_id, enabled, builder, note FROM shops"
        " WHERE kind = 'kitchen' AND key = 'amazon'"
    )
    assert tuple((await adb.execute(seeded)).one())[:3] == (None, False, "amazon")
    # As it's seeded it's nobody's change: the history starts empty.
    assert await adb.scalar(text("SELECT count(*) FROM revisions WHERE table_name = 'shops'")) == 0
    await adb.execute(text("DELETE FROM shops WHERE kind = 'kitchen'"))
    await adb.execute(
        text(
            "UPDATE shops SET affiliate_id = 'larder0b-20', enabled = true"
            " WHERE kind = 'bookseller' AND key = 'amazon'"
        )
    )
    await adb.run_sync(lambda session: migration.seed(session.connection()))
    tag, on, builder, note = (await adb.execute(seeded)).one()
    assert (tag, on, builder) == ("larder0b-20", False, "amazon")
    assert "Amazon Associate" in note
