"""Other names, merges and broader ingredients from linked Wikidata items
(wikidata_names.py)."""

import httpx2
import pytest
from sqlalchemy import text

from fake_wikidata import row
from openlarder.main import app
from openlarder.routers.foods import fdc_transport
from openlarder.wikidata_names import plain
from test_fdc import FakeFdc

ENTITY = "http://www.wikidata.org/entity/"


def test_only_plain_common_names() -> None:
    assert plain("brinjal") and plain("soft brown sugar") and plain("jalapeño")
    assert not plain("Allium cepa L.")
    assert not plain("Mel")
    assert not plain("onion plant")
    assert not plain("e160c")


@pytest.fixture
def usda() -> FakeFdc:
    fake = FakeFdc()
    app.dependency_overrides[fdc_transport] = lambda: httpx2.MockTransport(fake.handle)
    return fake


async def _id(adb, name: str) -> str:
    return str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": name}))


async def test_names_merges_and_parents(people, adb, usda, wikidata) -> None:
    ad, mo = await people("ad", role="admin"), await people("mo", role="moderator")
    await ad.post("/api/fdc/load")
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty"})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    for n, lines in enumerate(
        (["Onion", "Eggplant"], ["Onion", "Aubergine"], ["Onion", "Vegetable"])
    ):
        r = await mo.post(
            f"/api/sources/{book}/recipes",
            json={
                "title": f"Dish {n}",
                "editions": [{"edition_id": edition, "page": str(n + 1)}],
                "ingredients": lines,
            },
        )
        assert r.status_code == 201, r.text
    for item, label in (("Q23485", "onion"), ("Q7540", "eggplant"), ("Q11004", "vegetable")):
        wikidata.by_q.append(row(item, label=label))
    for name, item in (("Onion", "Q23485"), ("Eggplant", "Q7540"), ("Vegetable", "Q11004")):
        r = await mo.put(f"/api/ingredients/{await _id(adb, name)}/links", json={"wikidata": item})
        assert r.status_code == 200, r.text
    wikidata.names = [
        row("Q23485", label="onion", alias="bulb onion"),
        row("Q23485", label="onion", alias="Allium cepa L."),
        row("Q23485", label="onion", alias="onion plant"),
        row("Q23485", label="onion", uk="onion"),
        row("Q7540", label="eggplant", alias="brinjal"),
        # Another of our ingredients' name: a merge, not a name.
        row("Q7540", label="eggplant", uk="aubergine"),
        row("Q7540", label="eggplant", parent=f"{ENTITY}Q11004"),
        # A kind of something nothing is linked to: nothing.
        row("Q7540", label="eggplant", parent=f"{ENTITY}Q506"),
    ]

    r = await ad.post("/api/fdc/suggest")
    assert r.status_code == 200, r.text
    got = r.json()
    assert (got["names"], got["merges"], got["parents"]) == (2, 1, 1)

    page = (await mo.get("/api/fdc/suggestions", params={"show": "names"})).json()
    assert page["counts"]["names"] == 2
    rows = [
        (x["ingredient"]["name"], x["alias"]["name"], x["alias"]["region"]) for x in page["rows"]
    ]
    # The most used ingredient first.
    assert rows == [("Onion", "bulb onion", None), ("Eggplant", "brinjal", None)]
    brinjal = page["rows"][1]["alias"]
    assert brinjal["wikidata_id"] == "Q7540" and brinjal["url"].endswith("/Q7540")

    r = await mo.post("/api/fdc/suggestions/accept", json={"ids": [brinjal["id"]]})
    assert r.json() == {"done": 1, "skipped": 0}
    eggplant = await _id(adb, "Eggplant")
    got = (await mo.get(f"/api/ingredients/{eggplant}")).json()
    assert [a["name"] for a in got["aliases"]] == ["brinjal"]

    queue = (await mo.get("/api/suggestions")).json()["suggestions"]
    by_kind = {s["kind"]: s for s in queue}
    merge, parent = by_kind["merge"], by_kind["parent"]
    assert {merge["a"]["name"], merge["b"]["name"]} == {"Eggplant", "Aubergine"}
    assert merge["keep"] == "a" and merge["a"]["name"] == "Eggplant"
    assert "aubergine" in merge["reason"]
    assert (parent["a"]["name"], parent["b"]["name"], parent["decision"]) == (
        "Eggplant",
        "Vegetable",
        "a_under_b",
    )
    r = await mo.post(f"/api/suggestions/{parent['id']}/accept", json={})
    assert r.status_code == 200, r.text
    got = (await mo.get(f"/api/ingredients/{eggplant}")).json()
    assert got["parent"]["name"] == "Vegetable"

    # Again: nothing new; what's open stays, what's done isn't asked again.
    again = (await ad.post("/api/fdc/suggest")).json()
    assert (again["names"], again["merges"], again["parents"]) == (0, 0, 0)


async def test_a_uk_name_is_a_regional_alias(people, adb, usda, wikidata) -> None:
    ad, mo = await people("ad", role="admin"), await people("mo", role="moderator")
    await ad.post("/api/fdc/load")
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty"})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Bake",
            "editions": [{"edition_id": edition, "page": "1"}],
            "ingredients": ["Zucchini"],
        },
    )
    wikidata.by_q.append(row("Q7533", label="zucchini"))
    zucchini = await _id(adb, "Zucchini")
    await mo.put(f"/api/ingredients/{zucchini}/links", json={"wikidata": "Q7533"})
    wikidata.names = [row("Q7533", label="zucchini", uk="courgette")]
    assert (await ad.post("/api/fdc/suggest")).json()["names"] == 1
    [name] = (await mo.get("/api/fdc/suggestions", params={"show": "names"})).json()["rows"]
    assert (name["alias"]["name"], name["alias"]["region"]) == ("courgette", "UK")
    await mo.post("/api/fdc/suggestions/accept", json={"ids": [name["alias"]["id"]]})
    region = await adb.scalar(
        text("SELECT region FROM ingredient_aliases WHERE name = 'courgette'")
    )
    assert region == "UK"
