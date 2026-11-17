"""Shops for administrators (routers/shops.py): the booksellers and grocers
changed, added, put in order and switched on and off from the site.
*Decided by Ray, 2026-11-13.*"""

import pytest
from sqlalchemy import text

ISBN = "9780393541113"
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/140.0"}
WRAPPER = "https://click.example/deeplink?id=7&murl={url}"
AMAZON = {"label": "Amazon", "builder": "amazon", "affiliate_id": "openlarder-20", "enabled": True}
BOOKSHOP = {
    "label": "Bookshop.org",
    "builder": "bookshop",
    "affiliate_id": "12345",
    "product_template": "https://bookshop.org/a/{id}/{isbn13}",
    "enabled": True,
}


@pytest.fixture
async def book(adb):
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    edition = await adb.scalar(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:w, :i) RETURNING id"),
        {"w": work, "i": ISBN},
    )
    return {"work": work, "edition": edition}


def _all(groups: list[dict]) -> dict[tuple[str, str], dict]:
    return {(s["kind"], s["key"]): s for g in groups for s in g["shops"]}


async def _shops(admin) -> dict[tuple[str, str], dict]:
    response = await admin.get("/api/admin/shops")
    assert response.status_code == 200, response.text
    return _all(response.json())


async def _buy(client, book) -> list[str]:
    shown = (await client.get(f"/api/sources/{book['work']}")).json()
    return [b["retailer"] for b in shown["editions"][0]["buy"]]


async def _goes(client, path: str) -> str | None:
    response = await client.get(path, headers=BROWSER)
    return response.headers["location"] if response.status_code == 302 else None


async def test_only_an_administrator_sees_or_changes_the_shops(people, client) -> None:
    ann, mo = await people("ann", admin=True), await people("mo", role="moderator")
    amazon = (await _shops(ann))["bookseller", "amazon"]["id"]
    for who, refused in ((client, (401, 403)), (mo, (403,))):
        tried = [
            await who.get("/api/admin/shops"),
            await who.put(f"/api/admin/shops/{amazon}", json=AMAZON),
            await who.put(f"/api/admin/shops/{amazon}/enabled", json={"enabled": True}),
            await who.post(f"/api/admin/shops/{amazon}/move", json={"to": "up"}),
            await who.delete(f"/api/admin/shops/{amazon}"),
            await who.post(
                "/api/admin/shops",
                json={
                    "key": "corner",
                    "kind": "bookseller",
                    "label": "Corner",
                    "builder": "template",
                },
            ),
            await who.post(
                "/api/admin/shops/test", json={"key": "amazon", "kind": "bookseller", **AMAZON}
            ),
        ]
        assert all(r.status_code in refused for r in tried), [r.status_code for r in tried]
    # And nothing was changed.
    unchanged = (await _shops(ann))["bookseller", "amazon"]
    assert (unchanged["enabled"], unchanged["affiliate_id"]) == (False, None)


async def test_the_list_is_each_kind_in_order_with_its_clicks(people, adb, book) -> None:
    ann = await people("ann", admin=True)
    for n, days in enumerate((1, 2, 40)):
        await adb.execute(
            text(
                "INSERT INTO purchase_clicks (edition_id, retailer, clicked_at)"
                " VALUES (:e, 'bookshop', now() - make_interval(days => :d))"
            ),
            {"e": book["edition"], "d": days},
        )
        assert n < 3
    groups = (await ann.get("/api/admin/shops")).json()
    assert [(g["kind"], g["label"]) for g in groups] == [
        ("bookseller", "Booksellers"),
        ("grocer", "Grocers"),
        ("producer", "Producers"),
        ("kitchen", "Kitchen shops"),
    ]
    assert [s["key"] for s in groups[0]["shops"]] == [
        "bookshop",
        "bn",
        "thriftbooks",
        "bookoutlet",
        "amazon",
        "kobo",
    ]
    assert [s["label"] for s in groups[1]["shops"]] == ["Instacart", "Amazon Fresh", "Walmart"]
    bookshop = groups[0]["shops"][0]
    assert (bookshop["clicks_30_days"], bookshop["clicks"]) == (2, 3)
    # As first set up: off, nobody's.
    assert (bookshop["enabled"], bookshop["shown"], bookshop["updated_by"]) == (False, False, None)


async def test_a_changed_tag_is_on_the_next_click(people, client, book) -> None:
    ann = await people("ann", admin=True)
    amazon = (await _shops(ann))["bookseller", "amazon"]["id"]
    saved = await ann.put(f"/api/admin/shops/{amazon}", json=AMAZON)
    assert saved.status_code == 200, saved.text
    now = _all(saved.json())["bookseller", "amazon"]
    assert (now["enabled"], now["shown"], now["affiliate_id"], now["updated_by"]) == (
        True,
        True,
        "openlarder-20",
        "ann",
    )
    assert await _buy(client, book) == ["amazon"]
    assert await _goes(client, f"/go/amazon/{book['edition']}") == (
        "https://www.amazon.com/dp/0393541118?tag=openlarder-20"
    )
    # Changed: with no redeploy, and for this process at once.
    await ann.put(f"/api/admin/shops/{amazon}", json={**AMAZON, "affiliate_id": "larder0b-20"})
    assert await _goes(client, f"/go/amazon/{book['edition']}") == (
        "https://www.amazon.com/dp/0393541118?tag=larder0b-20"
    )
    # The grocer's Amazon is another shop, with a tag of its own.
    assert (await _shops(ann))["grocer", "amazon"]["affiliate_id"] is None


async def test_switched_off_its_buttons_go_and_come_back(people, client, book) -> None:
    ann = await people("ann", admin=True)
    listed = await _shops(ann)
    bookshop, amazon = listed["bookseller", "bookshop"]["id"], listed["bookseller", "amazon"]["id"]
    await ann.put(f"/api/admin/shops/{bookshop}", json=BOOKSHOP)
    await ann.put(f"/api/admin/shops/{amazon}", json=AMAZON)
    assert await _buy(client, book) == ["bookshop", "amazon"]

    off = await ann.put(f"/api/admin/shops/{bookshop}/enabled", json={"enabled": False})
    assert off.status_code == 200, off.text
    assert await _buy(client, book) == ["amazon"]
    assert await _goes(client, f"/go/bookshop/{book['edition']}") is None
    # Off, it keeps what it was set to.
    kept = _all(off.json())["bookseller", "bookshop"]
    assert (kept["enabled"], kept["shown"], kept["affiliate_id"]) == (False, False, "12345")

    await ann.put(f"/api/admin/shops/{bookshop}/enabled", json={"enabled": True})
    assert await _buy(client, book) == ["bookshop", "amazon"]


@pytest.mark.parametrize(
    ("key", "change", "says"),
    [
        ("bn", {"wrapper_template": "http://click.example/?u={url}"}, "starts https://"),
        ("bn", {"wrapper_template": "https://click.example/deeplink"}, "{url}"),
        ("bn", {"product_template": "www.barnesandnoble.com/w/?ean={isbn13}"}, "starts https://"),
        ("bn", {"product_template": "https://bn.example/?q={isbn}"}, "{isbn}"),
        ("bn", {"product_template": "https://bn.example/?q={term}"}, "{term}"),
        ("bn", {"wrapper_template": None}, "deep link"),
        ("bn", {"label": "  "}, "name"),
        ("bn", {"builder": "direct"}, None),
        ("bookshop", {"affiliate_id": "12a45"}, "number"),
        ("bookshop", {"affiliate_id": None}, "affiliate id"),
        ("amazon", {"affiliate_id": "tag&x=1"}, "Associates tag"),
        ("amazon", {"affiliate_id": "openlarder 20"}, "Associates tag"),
        ("amazon", {"affiliate_id": None}, "Associates tag"),
    ],
)
async def test_what_cant_work_is_refused_and_says_why(people, key, change, says) -> None:
    ann = await people("ann", admin=True)
    whole = {
        "bn": {
            "label": "Barnes & Noble",
            "builder": "wrapped",
            "wrapper_template": WRAPPER,
            "product_template": "https://www.barnesandnoble.com/w/?ean={isbn13}",
            "enabled": True,
        },
        "bookshop": BOOKSHOP,
        "amazon": AMAZON,
    }[key]
    shop = (await _shops(ann))["bookseller", key]["id"]
    assert (await ann.put(f"/api/admin/shops/{shop}", json=whole)).status_code == 200
    refused = await ann.put(f"/api/admin/shops/{shop}", json={**whole, **change})
    assert refused.status_code == 422, refused.text
    if says:
        assert says in refused.json()["detail"], refused.json()["detail"]
    # As it was before the try.
    kept = (await _shops(ann))["bookseller", key]
    assert {k: kept[k] for k in whole} == whole


async def test_a_grocers_address_takes_a_term_and_not_an_isbn(people, client, adb) -> None:
    ann = await people("ann", admin=True)
    walmart = (await _shops(ann))["grocer", "walmart"]["id"]
    body = {
        "label": "Walmart",
        "builder": "wrapped",
        "wrapper_template": WRAPPER,
        "product_template": "https://www.walmart.com/search?q={term}",
        "enabled": True,
    }
    assert (await ann.put(f"/api/admin/shops/{walmart}", json=body)).status_code == 200
    assert [g["key"] for g in (await client.get("/api/grocers")).json()] == ["walmart"]
    wrong = await ann.put(
        f"/api/admin/shops/{walmart}",
        json={**body, "product_template": "https://www.walmart.com/ip/{isbn13}"},
    )
    assert wrong.status_code == 422 and "{isbn13}" in wrong.json()["detail"]
    # A grocer has no format, whatever is sent.
    await ann.put(f"/api/admin/shops/{walmart}", json={**body, "format": "ebook"})
    assert (await _shops(ann))["grocer", "walmart"]["format"] is None


async def test_a_shop_is_added_last_with_a_key_for_good(people, client, book) -> None:
    ann = await people("ann", admin=True)
    corner = {
        "key": "corner-shop",
        "kind": "bookseller",
        "label": "  The Corner   Shop ",
        "builder": "template",
        "product_template": "https://corner.example/find?isbn={isbn13}",
        "earns": "none",
        "enabled": True,
    }
    added = await ann.post("/api/admin/shops", json=corner)
    assert added.status_code == 200, added.text
    booksellers = added.json()[0]["shops"]
    assert [s["key"] for s in booksellers][-1] == "corner-shop"
    new = booksellers[-1]
    assert (new["label"], new["format"], new["earns"], new["shown"], new["updated_by"]) == (
        "The Corner Shop",
        "print",
        "none",
        True,
        "ann",
    )
    assert await _buy(client, book) == ["corner-shop"]
    assert await _goes(client, f"/go/corner-shop/{book['edition']}") == (
        f"https://corner.example/find?isbn={ISBN}"
    )
    # People may put it in their order of shops.
    assert (await ann.put("/api/account/shops", json={"order": ["corner-shop"]})).status_code == 200

    again = await ann.post("/api/admin/shops", json=corner)
    assert again.status_code == 409 and "The Corner Shop" in again.json()["detail"]
    for bad in ("Corner Shop", "corner_shop", "", "x" * 41):
        r = await ann.post("/api/admin/shops", json={**corner, "key": bad})
        assert r.status_code == 422, bad
    # The same key among the grocers is another shop.
    grocer = await ann.post(
        "/api/admin/shops",
        json={
            "key": "corner-shop",
            "kind": "grocer",
            "label": "The Corner Shop",
            "builder": "template",
            "product_template": "https://corner.example/food?q={term}",
        },
    )
    assert grocer.status_code == 200, grocer.text
    # A change can't rename the key: it isn't among what's changed.
    changed = await ann.put(
        f"/api/admin/shops/{new['id']}",
        json={**{k: v for k, v in corner.items() if k != "kind"}, "key": "elsewhere"},
    )
    assert changed.status_code == 200
    assert "corner-shop" in [s["key"] for s in changed.json()[0]["shops"]]


async def test_shops_move_up_and_down_and_stop_at_the_ends(people) -> None:
    ann = await people("ann", admin=True)

    async def order() -> list[str]:
        return [s["key"] for (kind, _), s in (await _shops(ann)).items() if kind == "grocer"]

    assert await order() == ["instacart", "amazon", "walmart"]
    walmart = (await _shops(ann))["grocer", "walmart"]["id"]
    moved = await ann.post(f"/api/admin/shops/{walmart}/move", json={"to": "up"})
    assert moved.status_code == 200, moved.text
    assert await order() == ["instacart", "walmart", "amazon"]
    await ann.post(f"/api/admin/shops/{walmart}/move", json={"to": "up"})
    assert await order() == ["walmart", "instacart", "amazon"]
    # Past the top, nothing moves.
    await ann.post(f"/api/admin/shops/{walmart}/move", json={"to": "up"})
    assert await order() == ["walmart", "instacart", "amazon"]
    await ann.post(f"/api/admin/shops/{walmart}/move", json={"to": "down"})
    assert await order() == ["instacart", "walmart", "amazon"]
    # And the booksellers are as they were.
    assert [k for (kind, k) in await _shops(ann) if kind == "bookseller"][0] == "bookshop"
    assert (
        await ann.post(f"/api/admin/shops/{walmart}/move", json={"to": "sideways"})
    ).status_code == 422


async def test_a_shop_with_clicks_is_switched_off_not_deleted(people, adb, book) -> None:
    ann = await people("ann", admin=True)
    listed = await _shops(ann)
    kobo, bookshop = listed["bookseller", "kobo"]["id"], listed["bookseller", "bookshop"]["id"]
    await adb.execute(
        text("INSERT INTO purchase_clicks (edition_id, retailer) VALUES (:e, 'bookshop')"),
        {"e": book["edition"]},
    )
    refused = await ann.delete(f"/api/admin/shops/{bookshop}")
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Bookshop.org has 1 click recorded. Switch it off instead, so they keep their meaning."
    )
    gone = await ann.delete(f"/api/admin/shops/{kobo}")
    assert gone.status_code == 200, gone.text
    assert ("bookseller", "kobo") not in _all(gone.json())
    assert ("bookseller", "bookshop") in _all(gone.json())
    assert (await ann.delete(f"/api/admin/shops/{kobo}")).status_code == 404


async def test_each_change_is_in_the_history_and_an_administrators_to_undo(
    people, client, book
) -> None:
    ann, mo = await people("ann", admin=True), await people("mo", role="moderator")
    amazon = (await _shops(ann))["bookseller", "amazon"]["id"]
    await ann.put(f"/api/admin/shops/{amazon}", json=AMAZON)
    await ann.put(f"/api/admin/shops/{amazon}", json={**AMAZON, "affiliate_id": "larder0b-20"})

    changes = [
        c
        for c in (await mo.get("/api/changes")).json()
        if any(e["table"] == "shops" for e in c["entries"])
    ]
    assert len(changes) == 2
    latest = changes[0]
    assert latest["by"] == "ann"
    [entry] = latest["entries"]
    assert (entry["what"], entry["action"], entry["name"]) == ("shop", "changed", "Amazon")
    assert [(f["field"], f["before"], f["after"]) for f in entry["fields"]] == [
        ("affiliate_id", "openlarder-20", "larder0b-20")
    ]

    # A moderator sees it, and can't undo it: that would be changing a shop.
    refused = await mo.post(f"/api/changes/{latest['id']}/revert")
    assert refused.status_code == 403
    assert await _goes(client, f"/go/amazon/{book['edition']}") == (
        "https://www.amazon.com/dp/0393541118?tag=larder0b-20"
    )
    undone = await ann.post(f"/api/changes/{latest['id']}/revert")
    assert undone.status_code == 200, undone.text
    assert await _goes(client, f"/go/amazon/{book['edition']}") == (
        "https://www.amazon.com/dp/0393541118?tag=openlarder-20"
    )


async def test_a_link_is_tried_without_saving_or_counting(people, adb) -> None:
    ann = await people("ann", admin=True)
    tried = await ann.post(
        "/api/admin/shops/test",
        json={
            "key": "bn",
            "kind": "bookseller",
            "label": "Barnes & Noble",
            "builder": "wrapped",
            "wrapper_template": WRAPPER,
            "product_template": "https://www.barnesandnoble.com/w/?ean={isbn13}",
        },
    )
    assert tried.status_code == 200, tried.text
    assert tried.json() == {
        "url": "https://click.example/deeplink?id=7&murl="
        "https%3A%2F%2Fwww.barnesandnoble.com%2Fw%2F%3Fean%3D9780393541113",
        "host": "click.example",
        "sample": "“A Sample Cookbook” by Ann Author, ISBN 9780393541113",
    }
    grocer = await ann.post(
        "/api/admin/shops/test",
        json={"key": "amazon", "kind": "grocer", "label": "Amazon Fresh", **AMAZON},
    )
    assert grocer.json()["url"] == (
        "https://www.amazon.com/s?k=olive+oil&i=amazonfresh&tag=openlarder-20"
    )
    assert grocer.json()["sample"] == "the ingredient “olive oil”"
    # Nothing to try yet says what's missing.
    empty = await ann.post(
        "/api/admin/shops/test",
        json={"key": "bn", "kind": "bookseller", "label": "Barnes & Noble", "builder": "wrapped"},
    )
    assert empty.status_code == 422 and "deep link" in empty.json()["detail"]
    # Nothing saved, nothing counted.
    assert (await _shops(ann))["bookseller", "bn"]["wrapper_template"] is None
    assert await adb.scalar(text("SELECT count(*) FROM purchase_clicks")) == 0
