"""Producers (producers.py): added by an administrator, listed on their
page, shown on the ingredients they supply, and their clicks counted with
nothing about who clicked. *Ray, 2026-11-13.*

Against the real routes and database. What these can't show is the pages
themselves, which the accessibility check looks at.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from openlarder import dumps, producers, reset, shops

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/140.0"}
ADDRESS = "https://greenacre.example/?ref=openlarder"
NOTE = "If you order through this link you get $10 off, and OpenLarder's owner gets store credit."
FARM = {
    "label": "Green Acre Farm",
    "builder": "direct",
    "product_template": ADDRESS,
    "earns": "referral",
    "note": NOTE,
    "enabled": True,
    "description": "  Grass-fed beef and pastured pork\nfrom a family farm. ",
    "offer": "New customers get $10 off",
    "ships_to": ["wi", "MN", " il "],
}


async def _ingredient(adb, name: str, parent=None) -> str:
    return str(
        await adb.scalar(
            text(
                "INSERT INTO ingredients (name, match_key, parent_id)"
                " VALUES (:n, :k, :p) RETURNING id"
            ),
            {"n": name, "k": name.lower(), "p": parent},
        )
    )


def _producers(groups: list[dict]) -> dict[str, dict]:
    return {s["key"]: s for g in groups if g["kind"] == "producer" for s in g["shops"]}


async def _add(admin, key: str = "green-acre", **changes) -> dict:
    response = await admin.post(
        "/api/admin/shops", json={**FARM, "kind": "producer", "key": key, **changes}
    )
    assert response.status_code == 200, response.text
    return _producers(response.json())[key]


async def _listed(client) -> list[dict]:
    response = await client.get("/api/producers")
    assert response.status_code == 200, response.text
    return response.json()


async def _on_page(client, ingredient: str) -> list[str]:
    response = await client.get(f"/api/ingredients/{ingredient}")
    assert response.status_code == 200, response.text
    return [p["key"] for p in response.json()["producers"]]


# An administrator adds one


async def test_an_administrator_adds_a_producer_and_its_on_the_page(people, client, adb) -> None:
    ann = await people("ann", admin=True)
    beef, pork = await _ingredient(adb, "Beef"), await _ingredient(adb, "Pork")
    assert await _listed(client) == []
    assert (await client.get("/api/site")).json()["producers"] is False

    farm = await _add(ann, supplies=[pork, beef])
    assert (farm["kind"], farm["builder"], farm["shown"]) == ("producer", "direct", True)
    # Tidied as it's kept: the words run together, the codes in order.
    assert farm["description"] == "Grass-fed beef and pastured pork from a family farm."
    assert farm["ships_to"] == ["IL", "MN", "WI"]
    assert [s["name"] for s in farm["supplies"]] == ["Beef", "Pork"]
    assert (farm["affiliate_id"], farm["wrapper_template"], farm["format"]) == (None, None, None)

    assert await _listed(client) == [
        {
            "key": "green-acre",
            "label": "Green Acre Farm",
            "description": "Grass-fed beef and pastured pork from a family farm.",
            "offer": "New customers get $10 off",
            "ships": "Ships to 3 states",
            "earns": "referral",
            "disclosure": NOTE,
            "url": "/go/producer/green-acre",
            "supplies": [{"id": beef, "name": "Beef"}, {"id": pork, "name": "Pork"}],
            "states": ["Illinois", "Minnesota", "Wisconsin"],
        }
    ]
    assert (await client.get("/api/site")).json()["producers"] is True


async def test_the_groups_are_booksellers_grocers_and_producers(people) -> None:
    ann = await people("ann", admin=True)
    groups = (await ann.get("/api/admin/shops")).json()
    assert [(g["kind"], g["label"], len(g["shops"])) for g in groups] == [
        ("bookseller", "Booksellers", 6),
        ("grocer", "Grocers", 3),
        ("producer", "Producers", 0),
    ]


async def test_a_moderator_cant_add_one(people) -> None:
    mo = await people("mo", role="moderator")
    refused = await mo.post(
        "/api/admin/shops", json={**FARM, "kind": "producer", "key": "green-acre"}
    )
    assert refused.status_code == 403


@pytest.mark.parametrize(
    ("change", "says"),
    [
        ({"builder": "wrapped"}, "can't be made that way"),
        ({"builder": "template"}, "can't be made that way"),
        ({"product_template": "https://greenacre.example/?q={term}"}, "used as written"),
        ({"product_template": "http://greenacre.example/"}, "starts https://"),
        ({"product_template": "https://greenacre.example/a b"}, "no spaces"),
        ({"product_template": None}, "address"),
        ({"ships_to": ["WI", "ZZ"]}, "“ZZ”"),
        ({"ships_to": ["Wisconsin"]}, "two-letter code"),
        ({"note": None}, "what is earned and by whom"),
        ({"note": "   "}, "what is earned and by whom"),
        ({"label": " "}, "name"),
        ({"supplies": [str(uuid.uuid4())]}, "isn't in the catalog"),
    ],
)
async def test_what_cant_work_is_refused_and_says_why(people, change, says) -> None:
    ann = await people("ann", admin=True)
    refused = await ann.post(
        "/api/admin/shops", json={**FARM, "kind": "producer", "key": "green-acre", **change}
    )
    assert refused.status_code == 422, refused.text
    assert says in refused.json()["detail"], refused.json()["detail"]
    assert _producers((await ann.get("/api/admin/shops")).json()) == {}


async def test_one_that_earns_nothing_needs_no_note_and_says_so(people, client) -> None:
    ann = await people("ann", admin=True)
    await _add(ann, earns="none", note=None, ships_to=None, offer=None)
    [farm] = await _listed(client)
    assert farm["disclosure"] == "OpenLarder earns nothing from this link."
    assert (farm["ships"], farm["states"], farm["offer"]) == ("Ships everywhere", [], None)
    # Whatever was written for it: a link that earns nothing says that, in
    # the site's words.
    await _add(ann, "other-farm", earns="none", note="We love this farm.")
    other = (await _listed(client))[1]
    assert other["disclosure"] == "OpenLarder earns nothing from this link."


async def test_one_switched_off_may_be_unfinished(people, client) -> None:
    ann = await people("ann", admin=True)
    farm = await _add(ann, enabled=False, note=None, product_template=None)
    assert (farm["enabled"], farm["shown"]) == (False, False)
    assert await _listed(client) == []
    # And can't be switched on until it's whole.
    on = await ann.put(f"/api/admin/shops/{farm['id']}/enabled", json={"enabled": True})
    assert on.status_code == 422


async def test_a_bookseller_cant_take_the_producers_address(people) -> None:
    ann = await people("ann", admin=True)
    refused = await ann.post(
        "/api/admin/shops",
        json={
            "kind": "bookseller",
            "key": "producer",
            "label": "Producer Books",
            "builder": "template",
            "product_template": "https://books.example/{isbn13}",
        },
    )
    assert refused.status_code == 422 and "taken" in refused.json()["detail"]


async def test_its_link_is_tried_without_saving_or_counting(people, adb) -> None:
    ann = await people("ann", admin=True)
    tried = await ann.post(
        "/api/admin/shops/test", json={**FARM, "kind": "producer", "key": "green-acre"}
    )
    assert tried.status_code == 200, tried.text
    assert tried.json() == {
        "url": ADDRESS,
        "host": "greenacre.example",
        "sample": "anyone who follows it",
    }
    assert await adb.scalar(text("SELECT count(*) FROM shops WHERE kind = 'producer'")) == 0
    assert await adb.scalar(text("SELECT count(*) FROM producer_clicks")) == 0


async def test_changing_one_changes_what_it_supplies(people, client, adb) -> None:
    ann = await people("ann", admin=True)
    beef, pork, lamb = [await _ingredient(adb, n) for n in ("Beef", "Pork", "Lamb")]
    farm = await _add(ann, supplies=[beef, pork])
    changed = await ann.put(
        f"/api/admin/shops/{farm['id']}",
        json={**FARM, "label": "Green Acre", "supplies": [pork, lamb], "ships_to": []},
    )
    assert changed.status_code == 200, changed.text
    now = _producers(changed.json())["green-acre"]
    assert [s["name"] for s in now["supplies"]] == ["Lamb", "Pork"]
    assert (now["label"], now["ships_to"]) == ("Green Acre", None)
    [listed] = await _listed(client)
    assert [s["name"] for s in listed["supplies"]] == ["Lamb", "Pork"]
    assert listed["ships"] == "Ships everywhere"


async def test_a_shop_that_isnt_a_producer_takes_none_of_this(people, adb) -> None:
    ann = await people("ann", admin=True)
    beef = await _ingredient(adb, "Beef")
    added = await ann.post(
        "/api/admin/shops",
        json={
            "kind": "grocer",
            "key": "corner-shop",
            "label": "The Corner Shop",
            "builder": "template",
            "product_template": "https://corner.example/?q={term}",
            "description": "A shop on a corner.",
            "offer": "Free bag",
            "ships_to": ["WI"],
            "supplies": [beef],
        },
    )
    assert added.status_code == 200, added.text
    row = (
        await adb.execute(
            text("SELECT description, offer, ships_to FROM shops WHERE key = 'corner-shop'")
        )
    ).one()
    assert tuple(row) == (None, None, None)
    assert await adb.scalar(text("SELECT count(*) FROM producer_ingredients")) == 0


# Where it ships


@pytest.mark.parametrize(
    ("ships_to", "says"),
    [
        (None, "Ships everywhere"),
        ((), "Ships everywhere"),
        (("WI",), "Ships to Wisconsin only"),
        (("IL", "WI"), "Ships to 2 states"),
        (tuple(sorted(producers.STATES)[:30]), "Ships to 30 states"),
    ],
)
def test_where_it_ships_is_said_in_a_few_words(ships_to, says) -> None:
    shop = shops.Shop(
        key="x",
        kind="producer",
        label="X",
        builder="direct",
        affiliate_id=None,
        wrapper_template=None,
        product_template=ADDRESS,
        format=None,
        earns="none",
        note=None,
        enabled=True,
        position=0,
        ships_to=ships_to,
    )
    assert producers.ships(shop) == says


def test_the_states_are_the_fifty_and_the_district() -> None:
    assert len(producers.STATES) == 51
    assert producers.STATES["WI"] == "Wisconsin" and producers.STATES["DC"]
    assert all(len(code) == 2 and code.isupper() for code in producers.STATES)


# On an ingredient's page


async def test_a_producer_is_on_the_ingredients_it_supplies_and_those_under_them(
    people, client, adb
) -> None:
    ann = await people("ann", admin=True)
    meat = await _ingredient(adb, "Meat")
    beef = await _ingredient(adb, "Beef", parent=meat)
    ground = await _ingredient(adb, "Ground beef", parent=beef)
    chuck = await _ingredient(adb, "Ground chuck", parent=ground)
    butter = await _ingredient(adb, "Butter")
    await _add(ann, supplies=[beef])

    assert await _on_page(client, beef) == ["green-acre"]
    # Under it, and under that.
    assert await _on_page(client, ground) == ["green-acre"]
    assert await _on_page(client, chuck) == ["green-acre"]
    # Not what it's under, and not something else.
    assert await _on_page(client, meat) == []
    assert await _on_page(client, butter) == []

    card = (await client.get(f"/api/ingredients/{ground}")).json()["producers"][0]
    assert card == {
        "key": "green-acre",
        "label": "Green Acre Farm",
        "description": "Grass-fed beef and pastured pork from a family farm.",
        "offer": "New customers get $10 off",
        "ships": "Ships to 3 states",
        "earns": "referral",
        "disclosure": NOTE,
        "url": "/go/producer/green-acre",
    }


async def test_a_page_has_two_at_most_in_their_order(people, client, adb) -> None:
    ann = await people("ann", admin=True)
    beef = await _ingredient(adb, "Beef")
    ground = await _ingredient(adb, "Ground beef", parent=beef)
    await _add(ann, "first-farm", label="First Farm", supplies=[beef])
    await _add(ann, "second-farm", label="Second Farm", supplies=[ground])
    third = await _add(ann, "third-farm", label="Third Farm", supplies=[beef])
    assert await _on_page(client, ground) == ["first-farm", "second-farm"]
    # The Producers page has them all.
    assert [p["key"] for p in await _listed(client)] == ["first-farm", "second-farm", "third-farm"]

    for _ in range(2):
        moved = await ann.post(f"/api/admin/shops/{third['id']}/move", json={"to": "up"})
        assert moved.status_code == 200, moved.text
    assert await _on_page(client, ground) == ["third-farm", "first-farm"]
    assert [p["key"] for p in await _listed(client)] == ["third-farm", "first-farm", "second-farm"]


async def test_switched_off_its_gone_from_everywhere_and_comes_back(people, client, adb) -> None:
    ann = await people("ann", admin=True)
    beef = await _ingredient(adb, "Beef")
    farm = await _add(ann, supplies=[beef])
    off = await ann.put(f"/api/admin/shops/{farm['id']}/enabled", json={"enabled": False})
    assert off.status_code == 200, off.text
    assert await _listed(client) == [] and await _on_page(client, beef) == []
    assert (await client.get("/api/site")).json()["producers"] is False
    gone = await client.get("/go/producer/green-acre", headers=BROWSER)
    assert gone.status_code == 404 and gone.headers["cache-control"] == "no-store"

    await ann.put(f"/api/admin/shops/{farm['id']}/enabled", json={"enabled": True})
    assert [p["key"] for p in await _listed(client)] == ["green-acre"]
    assert await _on_page(client, beef) == ["green-acre"]


# A click


async def test_a_click_is_counted_and_sent_on_with_nothing_about_who(people, client, adb) -> None:
    ann = await people("ann", admin=True)
    await _add(ann)
    went = await ann.get(
        "/go/producer/green-acre", params={"from": "/ingredients/123?x=1"}, headers=BROWSER
    )
    assert went.status_code == 302 and went.headers["location"] == ADDRESS
    assert went.headers["cache-control"] == "no-store"

    columns = await adb.scalars(
        text(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'producer_clicks'"
        )
    )
    # Signed in as she is, the click has no account: there's nowhere to put one.
    assert set(columns) == {"id", "producer", "page", "clicked_at"}
    rows = (await adb.execute(text("SELECT producer, page FROM producer_clicks"))).all()
    assert [tuple(r) for r in rows] == [("green-acre", "/ingredients/123")]

    # A crawler is sent on, and not counted.
    crawler = await client.get("/go/producer/green-acre", headers={"User-Agent": "Googlebot/2.1"})
    assert crawler.status_code == 302
    assert await adb.scalar(text("SELECT count(*) FROM producer_clicks")) == 1
    # A producer there isn't.
    missing = await client.get("/go/producer/no-such-farm", headers=BROWSER)
    assert missing.status_code == 404 and missing.headers["cache-control"] == "no-store"
    assert await adb.scalar(text("SELECT count(*) FROM producer_clicks")) == 1


async def test_its_clicks_are_on_the_list_and_keep_it_from_being_deleted(
    people, client, adb
) -> None:
    ann = await people("ann", admin=True)
    beef = await _ingredient(adb, "Beef")
    farm = await _add(ann, supplies=[beef])
    other = await _add(ann, "other-farm", label="Other Farm", supplies=[beef])
    await client.get("/go/producer/green-acre", headers=BROWSER)
    await adb.execute(
        text(
            "INSERT INTO producer_clicks (producer, clicked_at)"
            " VALUES ('green-acre', now() - interval '40 days')"
        )
    )
    now = _producers((await ann.get("/api/admin/shops")).json())
    assert (now["green-acre"]["clicks_30_days"], now["green-acre"]["clicks"]) == (1, 2)
    assert (now["other-farm"]["clicks_30_days"], now["other-farm"]["clicks"]) == (0, 0)

    # And on the clicks report, by producer.
    report = (await ann.get("/api/admin/clicks")).json()
    assert report["producer_clicks"] == 1
    assert report["producers"] == [
        {"retailer": "green-acre", "label": "Green Acre Farm", "clicks": 1, "last_7_days": 1}
    ]

    kept = await ann.delete(f"/api/admin/shops/{farm['id']}")
    assert kept.status_code == 409 and "2 clicks" in kept.json()["detail"]
    # One nobody clicked goes, and what it supplied with it.
    gone = await ann.delete(f"/api/admin/shops/{other['id']}")
    assert gone.status_code == 200, gone.text
    assert list(_producers(gone.json())) == ["green-acre"]
    assert await adb.scalar(text("SELECT count(*) FROM producer_ingredients")) == 1


async def test_the_database_refuses_a_click_on_nothing(adb) -> None:
    with pytest.raises(DBAPIError):
        async with adb.begin_nested():
            await adb.execute(text("INSERT INTO producer_clicks (producer) VALUES ('')"))


# A private collection's ingredient is nobody's to list


async def _private_ingredient(owner, adb) -> str:
    """An ingredient only a private family collection uses."""
    box = await owner.post(
        "/api/sources/family", json={"title": "Secret Box", "acknowledged": True}
    )
    assert box.status_code == 200, box.text
    stew = await owner.post(
        f"/api/sources/{box.json()['id']}/recipes",
        json={"title": "Secret Stew", "ingredients": ["Zanzibar Moonsalt"]},
    )
    assert stew.status_code == 201, stew.text
    return str(
        await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Zanzibar Moonsalt'"))
    )


async def test_a_producer_cant_be_given_a_private_collections_ingredient(people, adb) -> None:
    ann = await people("ann", admin=True)
    salt = await _private_ingredient(ann, adb)
    # Her own collection's, which she can see and pick: refused all the same.
    refused = await ann.post(
        "/api/admin/shops",
        json={**FARM, "kind": "producer", "key": "green-acre", "supplies": [salt]},
    )
    assert refused.status_code == 422 and "everyone sees" in refused.json()["detail"]
    assert await adb.scalar(text("SELECT count(*) FROM producer_ingredients")) == 0


async def test_one_that_became_private_isnt_named_to_anyone_who_cant_see_it(
    people, client, adb
) -> None:
    """Picked while it was everyone's, a private collection's alone since:
    written here as the database would have it by then."""
    ann, bea = await people("ann", admin=True), await people("bea", admin=True)
    salt = await _private_ingredient(ann, adb)
    beef = await _ingredient(adb, "Beef")
    farm = await _add(bea, supplies=[beef])
    await adb.execute(
        text("INSERT INTO producer_ingredients (shop_id, ingredient_id) VALUES (:s, :i)"),
        {"s": uuid.UUID(farm["id"]), "i": uuid.UUID(salt)},
    )

    [listed] = await _listed(client)
    assert [s["name"] for s in listed["supplies"]] == ["Beef"]
    assert "Moonsalt" not in (await client.get("/api/producers")).text
    # Another administrator can't see her collection either.
    theirs = _producers((await bea.get("/api/admin/shops")).json())["green-acre"]
    assert [s["name"] for s in theirs["supplies"]] == ["Beef"]
    assert "Moonsalt" not in (await bea.get("/api/admin/shops")).text
    assert "Moonsalt" not in (await bea.get("/api/changes")).text
    # She can.
    hers = _producers((await ann.get("/api/admin/shops")).json())["green-acre"]
    assert [s["name"] for s in hers["supplies"]] == ["Beef", "Zanzibar Moonsalt"]


# The edit history, merges, dumps and resets


async def test_what_it_supplies_is_in_the_history_and_an_administrators_to_undo(
    people, client, adb
) -> None:
    ann, mo = await people("ann", admin=True), await people("mo", role="moderator")
    beef, pork = await _ingredient(adb, "Beef"), await _ingredient(adb, "Pork")
    farm = await _add(ann, supplies=[beef])
    await ann.put(f"/api/admin/shops/{farm['id']}", json={**FARM, "supplies": [beef, pork]})

    changes = [
        c
        for c in (await mo.get("/api/changes")).json()
        if any(e["table"] == "producer_ingredients" for e in c["entries"])
    ]
    assert len(changes) == 2
    latest = changes[0]
    assert latest["by"] == "ann"
    [entry] = [e for e in latest["entries"] if e["table"] == "producer_ingredients"]
    assert (entry["what"], entry["action"]) == ("ingredient a producer supplies", "added")
    # Named, the producer and the ingredient, not shown as ids.
    assert sorted((f["field"], f["after"]) for f in entry["fields"]) == [
        ("ingredient_id", "Pork"),
        ("shop_id", "Green Acre Farm"),
    ]

    # A moderator sees it, and can't undo it: that would be changing a shop.
    refused = await mo.post(f"/api/changes/{latest['id']}/revert")
    assert refused.status_code == 403
    assert await _on_page(client, pork) == ["green-acre"]
    undone = await ann.post(f"/api/changes/{latest['id']}/revert")
    assert undone.status_code == 200, undone.text
    assert await _on_page(client, pork) == []
    assert await _on_page(client, beef) == ["green-acre"]


async def test_merging_an_ingredient_keeps_its_producers(people, client, adb) -> None:
    ann = await people("ann", admin=True)
    mince, ground = await _ingredient(adb, "Beef mince"), await _ingredient(adb, "Ground beef")
    await _add(ann, "first-farm", label="First Farm", supplies=[mince])
    # This one supplies both: it keeps the one row.
    await _add(ann, "second-farm", label="Second Farm", supplies=[mince, ground])

    merged = await ann.post(f"/api/ingredients/{mince}/merge", json={"into": ground})
    assert merged.status_code == 200, merged.text
    assert await _on_page(client, ground) == ["first-farm", "second-farm"]
    rows = await adb.execute(
        text(
            "SELECT s.key, i.name FROM producer_ingredients p JOIN shops s ON s.id = p.shop_id"
            " JOIN ingredients i ON i.id = p.ingredient_id ORDER BY s.key"
        )
    )
    assert [tuple(r) for r in rows] == [
        ("first-farm", "Ground beef"),
        ("second-farm", "Ground beef"),
    ]


async def test_the_data_dump_has_no_producer(people, client, adb) -> None:
    ann = await people("ann", admin=True)
    beef = await _ingredient(adb, "Beef")
    await _add(ann, supplies=[beef])
    await client.get("/go/producer/green-acre", headers=BROWSER)
    rows = await dumps.read(adb)
    assert not {"shops", "producer_ingredients", "producer_clicks"} & set(rows)
    assert "Green Acre" not in repr(rows) and "greenacre.example" not in repr(rows)


async def test_a_catalog_reset_keeps_the_producer_and_empties_what_it_supplies(
    people, client, adb
) -> None:
    ann = await people("ann", admin=True)
    beef = await _ingredient(adb, "Beef")
    await _add(ann, supplies=[beef])
    await client.get("/go/producer/green-acre", headers=BROWSER)

    await reset.reset(adb)
    shops.reset()
    assert await adb.scalar(text("SELECT count(*) FROM producer_ingredients")) == 0
    assert await adb.scalar(text("SELECT count(*) FROM producer_clicks")) == 1
    [listed] = await _listed(client)
    assert (listed["key"], listed["supplies"]) == ("green-acre", [])

    await reset.reset(adb, everything=True)
    assert await adb.scalar(text("SELECT count(*) FROM producer_clicks")) == 0
    assert await adb.scalar(text("SELECT count(*) FROM shops WHERE kind = 'producer'")) == 1
