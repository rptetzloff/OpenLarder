"""Ingredients' grocery links (grocery.py), counting their clicks
(routers/go.py), and each person's grocer."""

from urllib.parse import unquote

import pytest
from sqlalchemy import text

from fake_broker import _settings
from openlarder import grocery

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/140.0"}
TEMPLATE = "https://partner.example/deeplink?murl={url}"


@pytest.fixture
def grocers(monkeypatch):
    monkeypatch.setattr(
        grocery,
        "get_settings",
        lambda: _settings(
            instacart_link=TEMPLATE, amazon_tag="openlarder-20", walmart_link=TEMPLATE
        ),
    )


async def _ingredient(adb, name: str, **more) -> str:
    columns = {"name": name, "match_key": name.lower(), **more}
    return str(
        await adb.scalar(
            text(
                f"INSERT INTO ingredients ({', '.join(columns)})"
                f" VALUES ({', '.join(':' + c for c in columns)}) RETURNING id"
            ),
            columns,
        )
    )


async def test_none_until_a_setting_is_in_place(client, adb) -> None:
    assert (await client.get("/api/grocers")).json() == []
    onion = await _ingredient(adb, "Yellow Onion")
    r = await client.get(f"/go/grocer/instacart/{onion}", headers=BROWSER)
    assert r.status_code == 404 and r.headers["cache-control"] == "no-store"


async def test_instacart_first_then_the_others(client, grocers) -> None:
    shown = (await client.get("/api/grocers")).json()
    assert [g["key"] for g in shown] == ["instacart", "amazon", "walmart"]
    assert shown[1]["label"] == "Amazon Fresh" and "Amazon Associate" in shown[1]["note"]


async def test_a_click_is_counted_and_sent_on(client, adb, grocers) -> None:
    onion = await _ingredient(adb, "Yellow Onion")
    r = await client.get(
        f"/go/grocer/instacart/{onion}", params={"from": "/recipes/abc"}, headers=BROWSER
    )
    assert r.status_code == 302 and r.headers["cache-control"] == "no-store"
    target = r.headers["location"]
    assert target.startswith("https://partner.example/deeplink?murl=")
    assert unquote(target.split("murl=")[1]) == "https://www.instacart.com/store/s?k=Yellow+Onion"
    r = await client.get(f"/go/grocer/amazon/{onion}", headers=BROWSER)
    assert r.headers["location"] == (
        "https://www.amazon.com/s?k=Yellow+Onion&i=amazonfresh&tag=openlarder-20"
    )
    clicks = (
        await adb.execute(text("SELECT grocer, page FROM grocery_clicks ORDER BY clicked_at"))
    ).all()
    assert sorted(clicks) == [("amazon", None), ("instacart", "/recipes/abc")]
    # A bot is sent on, uncounted.
    await client.get(f"/go/grocer/walmart/{onion}", headers={"User-Agent": "Googlebot/2.1"})
    assert await adb.scalar(text("SELECT count(*) FROM grocery_clicks")) == 2
    assert (await client.get(f"/go/grocer/kroger/{onion}", headers=BROWSER)).status_code == 404


async def test_the_shopping_term_is_searched_for(client, adb, grocers) -> None:
    eggs = await _ingredient(adb, "Egg", shopping_term="eggs, large")
    r = await client.get(f"/go/grocer/walmart/{eggs}", headers=BROWSER)
    assert unquote(r.headers["location"].split("murl=")[1]) == (
        "https://www.walmart.com/search?q=eggs%2C+large"
    )


async def test_each_person_chooses_a_grocer(people) -> None:
    ann = await people("ann")
    me = (await ann.put("/api/account/grocer", json={"grocer": "walmart"})).json()
    assert me["grocer"] == "walmart" and me["shops"] is None
    # Choosing the book shops keeps it.
    me = (await ann.put("/api/account/shops", json={"order": ["amazon"], "hidden": []})).json()
    assert me["grocer"] == "walmart" and me["shops"] == {"order": ["amazon"], "hidden": []}
    bad = await ann.put("/api/account/grocer", json={"grocer": "kroger"})
    assert bad.status_code == 422
    me = (await ann.put("/api/account/grocer", json={})).json()
    assert me["grocer"] is None and me["shops"]["order"] == ["amazon"]


async def test_admins_see_grocery_clicks(people, client, adb, grocers) -> None:
    ad = await people("ad", role="admin")
    onion = await _ingredient(adb, "Yellow Onion")
    for _ in range(2):
        await client.get(f"/go/grocer/instacart/{onion}", headers=BROWSER)
    page = (await ad.get("/api/admin/clicks")).json()
    assert page["grocery_clicks"] == 2
    assert page["grocers"][0]["label"] == "Instacart" and page["grocers"][0]["clicks"] == 2
    assert page["ingredients"] == [{"ingredient_id": onion, "name": "Yellow Onion", "clicks": 2}]
