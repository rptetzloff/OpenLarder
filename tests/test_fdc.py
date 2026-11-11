"""FoodData Central's generic foods, and ingredients linked to them and to
Wikidata (fdc.py, migration 0055)."""

import io
import zipfile

import httpx2
import pytest
from sqlalchemy import text

from fake_wikidata import row
from openlarder import fdc
from openlarder.main import app
from openlarder.routers.foods import fdc_transport

FOODS = [
    ("fdc_id", "data_type", "description", "food_category_id", "publication_date"),
    ("1001", "sr_legacy_food", "Onions, raw", "11", "2019-04-01"),
    ("1002", "sr_legacy_food", "Onions, sweet, raw", "11", "2019-04-01"),
    ("1003", "branded_food", "ACME ONION RINGS", "11", "2020-01-01"),
    ("1004", "foundation_food", "Onions, yellow, raw", "11", "2026-04-30"),
    ("1005", "sub_sample_food", "Onions, yellow, raw (sample 3)", "11", "2026-04-30"),
    ("1006", "survey_fndds_food", "Onion rings, from frozen", "3002", "2024-10-31"),
    ("1007", "sr_legacy_food", "Cheese,  cheddar", "1", "2019-04-01"),
]


def _zip(**files: list[tuple]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, rows in files.items():
            body = "\n".join(",".join(f'"{c}"' for c in r) for r in rows)
            z.writestr(f"FoodData_Central_test/{name}.csv", body)
    return out.getvalue()


DATASET = _zip(
    food=FOODS,
    food_category=[
        ("id", "code", "description"),
        ("1", "0100", "Dairy and Egg Products"),
        ("11", "1100", "Vegetables and Vegetable Products"),
    ],
    wweia_food_category=[
        ("wweia_food_category", "wweia_food_category_description"),
        ("3002", "Fried vegetables"),
    ],
    sr_legacy_food=[("fdc_id", "NDB_number"), ("1001", "11282")],
)


class FakeFdc:
    def __init__(self) -> None:
        self.status = 200
        self.asked: list[str] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.asked.append(str(request.url))
        if self.status != 200:
            return httpx2.Response(self.status)
        return httpx2.Response(200, content=DATASET)


@pytest.fixture
def usda() -> FakeFdc:
    fake = FakeFdc()
    app.dependency_overrides[fdc_transport] = lambda: httpx2.MockTransport(fake.handle)
    return fake


def test_only_generic_foods_are_read() -> None:
    foods = {f.fdc_id: f for f in fdc.read(DATASET)}
    assert sorted(foods) == [1001, 1002, 1004, 1006, 1007]
    assert foods[1001].category == "Vegetables and Vegetable Products"
    assert foods[1001].ndb_number == 11282 and foods[1002].ndb_number is None
    assert foods[1006].category == "Fried vegetables"
    assert foods[1007].description == "Cheese, cheddar"
    with pytest.raises(fdc.BadDataset):
        fdc.read(b"not a zip")
    with pytest.raises(fdc.BadDataset):
        fdc.read(_zip(other=[("a",), ("b",)]))


async def test_an_administrator_loads_them(people, usda) -> None:
    ad, mo = await people("ad", role="admin"), await people("mo", role="moderator")
    assert (await mo.post("/api/fdc/load")).status_code == 403
    assert (await ad.get("/api/fdc")).json() == {"foods": 0, "loaded_at": None}
    r = await ad.post("/api/fdc/load")
    assert r.status_code == 200 and r.json()["foods"] == 5, r.text
    # Every dataset set, and again without doubling anything.
    assert len(usda.asked) == 3
    assert (await ad.post("/api/fdc/load")).json()["foods"] == 5
    usda.status = 404
    r = await ad.post("/api/fdc/load")
    assert r.status_code == 503 and "404" in r.json()["detail"]


async def test_a_moderator_finds_a_food(people, usda) -> None:
    ad, mo = await people("ad", role="admin"), await people("mo", role="moderator")
    con = await people("con", role="contributor")
    await ad.post("/api/fdc/load")
    assert (await con.get("/api/fdc/foods", params={"q": "onion"})).status_code == 403
    found = (await mo.get("/api/fdc/foods", params={"q": "onions raw"})).json()
    assert [f["fdc_id"] for f in found][:1] == [1001]
    assert {f["fdc_id"] for f in found} == {1001, 1002, 1004}
    assert found[0]["url"] == "https://fdc.nal.usda.gov/food-details/1001/nutrients"
    assert [f["fdc_id"] for f in (await mo.get("/api/fdc/foods", params={"q": "1007"})).json()] == [
        1007
    ]
    assert (await mo.get("/api/fdc/foods", params={"q": "100%"})).json() == []
    # A plural finds the singular FDC writes.
    assert 1007 in {
        f["fdc_id"] for f in (await mo.get("/api/fdc/foods", params={"q": "cheeses"})).json()
    }


async def _ingredient(adb, name: str, key: str) -> str:
    return str(
        await adb.scalar(
            text("INSERT INTO ingredients (name, match_key) VALUES (:n, :k) RETURNING id"),
            {"n": name, "k": key},
        )
    )


async def test_linking_an_ingredient(people, client, adb, usda, wikidata) -> None:
    ad, mo = await people("ad", role="admin"), await people("mo", role="moderator")
    await ad.post("/api/fdc/load")
    wikidata.by_q.append(row("Q23485", label="onion", description="vegetable"))
    onion = await _ingredient(adb, "Yellow Onion", "yellow onion")
    other = await _ingredient(adb, "Brown Onion", "brown onion")
    url = f"/api/ingredients/{onion}/links"

    assert (await client.put(url, json={"fdc_id": 1004})).status_code in (401, 403)
    r = await mo.put(url, json={"fdc_id": 1004, "wikidata": "https://www.wikidata.org/wiki/Q23485"})
    assert r.status_code == 200, r.text
    got = (await client.get(f"/api/ingredients/{onion}")).json()
    assert got["fdc"] == {
        "fdc_id": 1004,
        "description": "Onions, yellow, raw",
        "data_type": "foundation_food",
        "category": "Vegetables and Vegetable Products",
        "url": "https://fdc.nal.usda.gov/food-details/1004/nutrients",
    }
    assert got["wikidata"] == {
        "id": "Q23485",
        "label": "onion",
        "url": "https://www.wikidata.org/wiki/Q23485",
    }
    assert got["same_records"] == []

    # Another linked to the same item: likely one ingredient.
    await mo.put(f"/api/ingredients/{other}/links", json={"wikidata": "Q23485"})
    got = (await client.get(f"/api/ingredients/{onion}")).json()
    assert [s["name"] for s in got["same_records"]] == ["Brown Onion"]

    bad = await mo.put(url, json={"fdc_id": 999})
    assert bad.status_code == 422 and "Admin" in bad.json()["detail"]
    assert (await mo.put(url, json={"wikidata": "Q999999999"})).status_code == 422
    assert (await mo.put(url, json={"wikidata": "onion"})).status_code == 422
    # Unlinking.
    assert (await mo.put(url, json={})).status_code == 200
    got = (await client.get(f"/api/ingredients/{onion}")).json()
    assert (got["fdc"], got["wikidata"]) == (None, None)


async def test_a_merge_keeps_the_links(people, client, adb, usda, wikidata) -> None:
    ad, mo = await people("ad", role="admin"), await people("mo", role="moderator")
    await ad.post("/api/fdc/load")
    wikidata.by_q.append(row("Q23485", label="onion"))
    gone = await _ingredient(adb, "Onions", "onions")
    kept = await _ingredient(adb, "Onion", "onion")
    await mo.put(f"/api/ingredients/{gone}/links", json={"fdc_id": 1001, "wikidata": "Q23485"})
    await mo.put(f"/api/ingredients/{kept}/links", json={"fdc_id": 1004})
    r = await mo.post(f"/api/ingredients/{gone}/merge", json={"into": kept})
    assert r.status_code == 200, r.text
    got = (await client.get(f"/api/ingredients/{kept}")).json()
    # Its own FDC food, and the Wikidata item it lacked.
    assert (got["fdc"]["fdc_id"], got["wikidata"]["id"]) == (1004, "Q23485")
