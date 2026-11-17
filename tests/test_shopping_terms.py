"""Setting what a Shop link searches for, from an ingredient's page and a
piece of equipment's (routers/ingredients.py, routers/equipment.py): the
column was there for both with nothing on the site that set it. Where a
link then goes is test_grocery.py's and test_kitchen_shops.py's."""

from urllib.parse import unquote

import pytest
from sqlalchemy import text

from openlarder import shops

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/140.0"}
TEMPLATE = "https://partner.example/deeplink?murl={url}"
# Each kind's list, a name in it, its table, and the shop its links go to.
KINDS = {
    "ingredients": (
        "Egg",
        "ingredients",
        "/go/grocer/walmart/",
        "https://www.walmart.com/search?q=",
    ),
    "equipment": (
        "Dutch oven",
        "equipment",
        "/go/equipment/panhandle/",
        "https://panhandle.example/search?q=",
    ),
}


@pytest.fixture
async def shop(adb):
    """A grocer and a kitchen shop, each switched on with its setting."""
    await adb.execute(
        text(
            "UPDATE shops SET wrapper_template = :w, enabled = true"
            " WHERE kind = 'grocer' AND key = 'walmart'"
        ),
        {"w": TEMPLATE},
    )
    await adb.execute(
        text(
            "INSERT INTO shops (kind, key, label, builder, wrapper_template, product_template,"
            " enabled, position) VALUES ('kitchen', 'panhandle', 'Panhandle', 'wrapped', :w,"
            " 'https://panhandle.example/search?q={term}', true, 1)"
        ),
        {"w": TEMPLATE},
    )
    await adb.execute(
        text(
            "INSERT INTO ingredients (name, match_key) VALUES ('Egg', 'egg') ON CONFLICT DO NOTHING"
        )
    )
    shops.reset()
    yield
    shops.reset()


async def _id(adb, table: str, name: str) -> str:
    return str(await adb.scalar(text(f"SELECT id FROM {table} WHERE name = :n"), {"n": name}))


async def _stored(adb, table: str, one: str) -> str | None:
    return await adb.scalar(text(f"SELECT shopping_term FROM {table} WHERE id = :i"), {"i": one})


async def _searched(client, go: str, one: str) -> str:
    """What a click on its Shop link searches the shop for."""
    sent = await client.get(f"{go}{one}", headers=BROWSER)
    assert sent.status_code in (302, 303, 307), sent.text
    return unquote(sent.headers["location"].split("murl=")[1])


@pytest.mark.parametrize("kind", list(KINDS))
async def test_a_moderator_says_what_a_shop_link_searches_for(
    kind, people, client, adb, shop
) -> None:
    name, table, go, search = KINDS[kind]
    mo = await people("mo", role="moderator")
    one = await _id(adb, table, name)
    address = f"/api/{kind}/{one}/shopping-term"
    # Until it's said, the name.
    assert (await client.get(f"/api/{kind}/{one}")).json()["shopping_term"] is None
    assert await _searched(client, go, one) == search + name.replace(" ", "+")

    said = await mo.put(address, json={"term": "  large   brown eggs "})
    assert said.status_code == 200, said.text
    assert said.json() == {"id": one, "name": name}
    # Kept with its spaces tidied, on the page for anyone, and searched for.
    assert await _stored(adb, table, one) == "large brown eggs"
    assert (await client.get(f"/api/{kind}/{one}")).json()["shopping_term"] == "large brown eggs"
    assert await _searched(client, go, one) == search + "large+brown+eggs"

    # Nothing, spaces, or the name again in any case put it back to the
    # name: nothing is kept, so a later rename is searched for.
    for back in (None, "", "   ", name.upper(), f" {name} "):
        await mo.put(address, json={"term": "something"})
        assert (await mo.put(address, json={"term": back})).status_code == 200, back
        assert await _stored(adb, table, one) is None, back
    assert await _searched(client, go, one) == search + name.replace(" ", "+")

    # As long as a name may be, and no longer.
    assert (await mo.put(address, json={"term": "x" * shops.MAX_TERM})).status_code == 200
    assert (await mo.put(address, json={"term": "x" * (shops.MAX_TERM + 1)})).status_code == 422
    assert await _stored(adb, table, one) == "x" * shops.MAX_TERM


@pytest.mark.parametrize("kind", list(KINDS))
async def test_only_a_moderator_sets_it_and_only_for_what_they_can_see(
    kind, people, client, adb, shop
) -> None:
    name, table, _, _ = KINDS[kind]
    one = await _id(adb, table, name)
    address = f"/api/{kind}/{one}/shopping-term"
    ann = await people("ann")
    con = await people("con", role="contributor")
    assert (await client.put(address, json={"term": "eggs"})).status_code == 401
    for other in (ann, con):
        assert (await other.put(address, json={"term": "eggs"})).status_code == 403
    assert await _stored(adb, table, one) is None

    # What only a family's recipe brought in is theirs: a moderator is told
    # there's no such thing, and nothing is changed.
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    made = await ann.post(
        f"/api/sources/{box}/recipes",
        json={"title": "Nana's", "ingredients": ["moonbeam dust"], "equipment": ["moonbeam press"]},
    )
    assert made.status_code == 201, made.text
    hers = str(
        await adb.scalar(
            text(f"SELECT id FROM {table} WHERE match_key = :k"),
            {"k": "moonbeam dust" if kind == "ingredients" else "moonbeam press"},
        )
    )
    mo = await people("mo", role="moderator")
    refused = await mo.put(f"/api/{kind}/{hers}/shopping-term", json={"term": "found you"})
    assert refused.status_code == 404
    assert await _stored(adb, table, hers) is None


@pytest.mark.parametrize("kind", list(KINDS))
async def test_a_term_is_in_the_history_and_a_merge_keeps_it(
    kind, people, client, adb, shop
) -> None:
    name, table, _, _ = KINDS[kind]
    mo = await people("mo", role="moderator")
    one = await _id(adb, table, name)
    await mo.put(f"/api/{kind}/{one}/shopping-term", json={"term": "eggs, large"})
    history = (await client.get(f"/api/{kind}/{one}/history")).json()
    fields = [f for change in history for e in change["entries"] for f in e["fields"]]
    assert {"field": "shopping_term", "before": None, "after": "eggs, large"} in fields, history
    assert history[0]["by"] == "mo"

    # Merged into one with no term of its own, the term goes with it; one
    # that has its own keeps it.
    other = "Hen's egg" if kind == "ingredients" else "Casserole pot"
    made = await adb.scalar(
        text(f"INSERT INTO {table} (name, match_key) VALUES (:n, :k) RETURNING id"),
        {"n": other, "k": other.lower()},
    )
    merged = await mo.post(f"/api/{kind}/{one}/merge", json={"into": str(made)})
    assert merged.status_code == 200, merged.text
    assert await _stored(adb, table, str(made)) == "eggs, large"
    third = await adb.scalar(
        text(
            f"INSERT INTO {table} (name, match_key, shopping_term)"
            " VALUES ('Third thing', 'third thing', 'its own') RETURNING id"
        )
    )
    again = await mo.post(f"/api/{kind}/{made}/merge", json={"into": str(third)})
    assert again.status_code == 200, again.text
    assert await _stored(adb, table, str(third)) == "its own"
