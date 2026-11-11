"""Suggested links from ingredients to FoodData Central and Wikidata
(fdc_match.py), and deciding them (Admin › Ingredient links)."""

import httpx2
import pytest
from sqlalchemy import text

from fake_wikidata import row
from openlarder.fdc_match import Foods
from openlarder.main import app
from openlarder.models import FdcFood
from openlarder.routers.foods import fdc_transport
from test_fdc import FakeFdc


def _foods(*described: tuple[str, str]) -> Foods:
    return Foods(
        FdcFood(fdc_id=i, description=d, data_type=t) for i, (d, t) in enumerate(described, start=1)
    )


def _best(foods: Foods, name: str) -> tuple[str, str] | None:
    found = foods.matches(name)
    return (found[0].food.description, found[0].certainty) if found else None


SR, FOUNDATION, SURVEY = "sr_legacy_food", "foundation_food", "survey_fndds_food"


def test_the_words_decide() -> None:
    foods = _foods(
        ("Onions, raw", SR),
        ("Onions, yellow, raw", FOUNDATION),
        ("Chocolate milk, NFS", SURVEY),
        ("Chicken, meatless", SR),
        ("Spices, cinnamon, ground", SR),
        ("Flour, 00", FOUNDATION),
        ("Oil, olive, salad or cooking", SR),
        ("Cheese, cheddar", FOUNDATION),
        ("Cheese, cheddar", SR),
    )
    # Plurals and plain words ("raw") don't count against it.
    assert _best(foods, "Onions") == ("Onions, raw", "likely")
    assert _best(foods, "Yellow Onion") == ("Onions, yellow, raw", "likely")
    # A two-word head reads in order.
    assert _best(foods, "Milk Chocolate") is None
    # A word saying it's something else.
    assert _best(foods, "Chicken") is None
    # After a category, how a spice is sold isn't a word more.
    assert _best(foods, "Cinnamon") == ("Spices, cinnamon, ground", "likely")
    # One word more is unsure; two, nothing.
    assert _best(foods, "Flour") == ("Flour, 00", "unsure")
    assert _best(foods, "Olive Oil") is None
    # Foundation before SR Legacy.
    assert foods.matches("Cheddar Cheese")[0].food.data_type == FOUNDATION


@pytest.fixture
def usda() -> FakeFdc:
    fake = FakeFdc()
    app.dependency_overrides[fdc_transport] = lambda: httpx2.MockTransport(fake.handle)
    return fake


async def _cook(mo, adb, lines) -> None:
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty"})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    for n, title in enumerate(("Soup", "Tart", "Stew")):
        r = await mo.post(
            f"/api/sources/{book}/recipes",
            json={
                "title": title,
                "editions": [{"edition_id": edition, "page": str(n + 1)}],
                # Onion in all three, so it's the most used.
                "ingredients": ["Onion", *lines[: n + 1]],
            },
        )
        assert r.status_code == 201, r.text


async def _id(adb, name: str) -> str:
    return str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": name}))


async def test_suggesting_and_deciding(people, adb, usda, wikidata) -> None:
    ad, mo = await people("ad", role="admin"), await people("mo", role="moderator")
    con = await people("con", role="contributor")
    assert (await ad.post("/api/fdc/suggest")).status_code == 409
    await ad.post("/api/fdc/load")
    await _cook(mo, adb, ["Yellow Onion", "Cheddar Cheese", "Saffron Threads"])
    wikidata.by_ndb = [row("Q23485", ndb="11282", label="onion")]

    assert (await mo.post("/api/fdc/suggest")).status_code == 403
    r = await ad.post("/api/fdc/suggest")
    assert r.json() == {"fdc": 3, "wikidata": 1}, r.text
    # Nothing new a second time.
    assert (await ad.post("/api/fdc/suggest")).json() == {"fdc": 0, "wikidata": 0}

    assert (await con.get("/api/fdc/suggestions")).status_code == 403
    page = (await mo.get("/api/fdc/suggestions")).json()
    assert page["counts"] == {"likely": 3, "unsure": 0, "wikidata": 1}
    names = [(r["ingredient"]["name"], r["fdc"]["food"]["description"]) for r in page["rows"]]
    # The most used first.
    assert names[0] == ("Onion", "Onions, raw")
    assert set(names[1:]) == {
        ("Yellow Onion", "Onions, yellow, raw"),
        ("Cheddar Cheese", "Cheese, cheddar"),
    }
    onion = page["rows"][0]
    assert onion["wikidata"]["wikidata_id"] == "Q23485"
    assert onion["wikidata"]["certainty"] == "unsure"
    assert [
        r["ingredient"]["name"]
        for r in (await mo.get("/api/fdc/suggestions", params={"show": "wikidata"})).json()["rows"]
    ] == ["Onion"]

    ids = [onion["fdc"]["id"], onion["wikidata"]["id"]]
    r = await mo.post("/api/fdc/suggestions/accept", json={"ids": ids})
    assert r.json() == {"done": 2, "skipped": 0}
    got = (await mo.get(f"/api/ingredients/{await _id(adb, 'Onion')}")).json()
    assert (got["fdc"]["fdc_id"], got["wikidata"]["id"]) == (1001, "Q23485")
    newest = (await mo.get(f"/api/ingredients/{await _id(adb, 'Onion')}/history")).json()[0]
    assert newest["by"] == "mo" and newest["via"] == "link-suggestion"
    # Decided already.
    assert (await mo.post("/api/fdc/suggestions/accept", json={"ids": ids})).json() == {
        "done": 0,
        "skipped": 2,
    }

    yellow = next(r for r in page["rows"] if r["ingredient"]["name"] == "Yellow Onion")
    r = await mo.post("/api/fdc/suggestions/dismiss", json={"ids": [yellow["fdc"]["id"]]})
    assert r.json() == {"done": 1, "skipped": 0}
    # Not suggested again.
    assert (await ad.post("/api/fdc/suggest")).json() == {"fdc": 0, "wikidata": 0}

    # Linked by hand meanwhile: accepting skips it.
    cheddar = next(r for r in page["rows"] if r["ingredient"]["name"] == "Cheddar Cheese")
    await mo.put(f"/api/ingredients/{cheddar['ingredient']['id']}/links", json={"fdc_id": 1002})
    r = await mo.post("/api/fdc/suggestions/accept", json={"ids": [cheddar["fdc"]["id"]]})
    assert r.json() == {"done": 0, "skipped": 1}
    # And it isn't listed any more.
    assert (await mo.get("/api/fdc/suggestions")).json()["counts"]["likely"] == 0
