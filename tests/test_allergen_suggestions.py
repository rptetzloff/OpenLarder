"""Allergens suggested from ingredients' names (allergen_rules.py), and
deciding them in the Suggestions queue."""

from sqlalchemy import text

from openlarder.allergen_rules import read


def _said(name: str) -> dict[str, tuple[str, bool]]:
    return {k: (f.status, f.likely) for k, f in read(name, "name").items()}


def test_names_say_what_they_contain() -> None:
    assert _said("Unsalted Butter") == {"milk": ("contains", True)}
    assert _said("Peanut Butter") == {"peanuts": ("contains", True)}
    assert _said("Free-range Eggs") == {"egg": ("contains", True)}
    assert _said("Oats") == {"gluten": ("may_contain", False)}
    # Every gluten grain is gluten; only wheat and its kin are wheat.
    assert _said("Rye Flour") == {"gluten": ("contains", True)}
    assert _said("Pearl Barley") == {"gluten": ("contains", True)}
    for wheat in ("Couscous", "Spelt Flour", "Freekeh", "Farina", "Matzo Meal", "Triticale"):
        assert _said(wheat) == {
            "wheat": ("contains", True),
            "gluten": ("contains", True),
        }, wheat
    assert _said("Soy Sauce") == {
        "soy": ("contains", True),
        "wheat": ("contains", False),
        "gluten": ("contains", False),
    }
    for nothing in (
        "Vegan Butter",
        "Coconut Milk",
        "Cream of Tartar",
        "Butter Beans",
        "Eggplant",
        "Oyster Mushrooms",
        "Gluten-free Flour",
        "Rice Noodles",
        "Buckwheat Flour",
    ):
        assert _said(nothing) == {}, nothing


def test_names_say_meat_poultry_and_pork() -> None:
    """Ray, 2026-11-11: recorded as allergens are; poultry is one."""
    for poultry in ("Chicken Stock", "Ground Turkey", "Duck Fat", "Cornish Game Hen", "Foie Gras"):
        assert _said(poultry) == {"poultry": ("contains", True)}, poultry
    for meat in ("Ground Beef", "Leg of Lamb", "Veal Stock", "Oxtail"):
        assert _said(meat) == {"meat": ("contains", True)}, meat
    assert _said("Flank Steak") == {"meat": ("contains", False)}
    for pork in ("Bacon", "Lard", "Pork Shoulder", "Prosciutto", "Ham Hock"):
        assert _said(pork) == {"pork": ("contains", True)}, pork
    assert _said("Italian Sausage") == {"pork": ("contains", False)}
    assert _said("Chicken Sausage") == {"poultry": ("contains", True)}
    assert _said("Turkey Bacon") == {"poultry": ("contains", True)}
    assert _said("Powdered Gelatin") == {
        "meat": ("may_contain", False),
        "pork": ("may_contain", False),
    }
    assert _said("Goat Cheese") == {"milk": ("contains", True)}
    assert _said("Tuna Steak") == {"fish": ("contains", True)}
    for nothing in (
        "Poultry Seasoning",
        "Chicken of the Woods",
        "Duck Sauce",
        "Vegetarian Sausage",
        "Cauliflower Steak",
        "Beefsteak Tomato",
        "Hamburger Bun",
        "Vegetable Stock",
    ):
        assert not {"meat", "poultry", "pork"} & set(_said(nothing)), nothing
    assert _said("Duck Egg") == {"egg": ("contains", True)}


async def _book(mo, adb, lines: list[str]) -> None:
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty"})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Everything",
            "editions": [{"edition_id": edition, "page": "1"}],
            "ingredients": lines,
        },
    )
    assert r.status_code == 201, r.text


async def _id(adb, name: str) -> str:
    return str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": name}))


async def _queue(mo) -> dict[tuple[str, str], dict]:
    page = (await mo.get("/api/suggestions", params={"kind": "allergen"})).json()
    return {(s["a"]["name"], s["allergen"]["key"]): s for s in page["suggestions"]}


async def test_suggested_accepted_dismissed_and_not_asked_again(people, adb) -> None:
    ad, mo = await people("ad", role="admin"), await people("mo", role="moderator")
    await _book(
        mo, adb, ["Cheese", "Cheddar", "Peanut Butter", "Vegan Butter", "Tofu", "Oats", "Apple"]
    )
    cheese, cheddar, tofu = [await _id(adb, n) for n in ("Cheese", "Cheddar", "Tofu")]
    await mo.put(f"/api/ingredients/{cheddar}/parent", json={"parent": cheese})
    # Recorded already: not suggested.
    await mo.put(f"/api/ingredients/{tofu}/allergens", json={"statuses": {"soy": "contains"}})

    assert (await mo.post("/api/suggestions/allergens")).status_code == 403
    r = await ad.post("/api/suggestions/allergens")
    assert r.status_code == 200, r.text
    assert r.json() == {"suggested": 3}
    queue = await _queue(mo)
    # Cheddar is covered by Cheese's; Vegan Butter says it isn't.
    assert set(queue) == {("Cheese", "milk"), ("Peanut Butter", "peanuts"), ("Oats", "gluten")}
    milk = queue[("Cheese", "milk")]
    assert milk["allergen"]["status"] == "contains" and milk["certainty"] == "likely"
    assert milk["actionable"] and "“cheese”" in milk["reason"]
    oats = queue[("Oats", "gluten")]
    assert oats["allergen"]["status"] == "may_contain" and oats["certainty"] is None
    # Likely ones first.
    page = (await mo.get("/api/suggestions", params={"kind": "allergen"})).json()
    assert page["suggestions"][-1]["a"]["name"] == "Oats"

    r = await mo.post(f"/api/suggestions/{milk['id']}/accept", json={})
    assert r.status_code == 200, r.text
    got = (await mo.get(f"/api/ingredients/{cheddar}")).json()["allergens"]
    assert [(a["key"], a["status"], a["inherited"]) for a in got] == [("milk", "contains", True)]
    history = (await mo.get(f"/api/ingredients/{cheese}/history")).json()
    assert history[0]["via"] == f"suggestion:{milk['id']}"

    await mo.post(f"/api/suggestions/{oats['id']}/dismiss")
    assert (await ad.post("/api/suggestions/allergens")).json() == {"suggested": 0}
    assert set(await _queue(mo)) == {("Peanut Butter", "peanuts")}


async def test_a_page_of_likely_ones_at_once(people, adb) -> None:
    ad, mo = await people("ad", role="admin"), await people("mo", role="moderator")
    await _book(mo, adb, ["Butter", "Sesame Seeds", "Celery", "Shrimp"])
    await ad.post("/api/suggestions/allergens")
    queue = await _queue(mo)
    assert len(queue) == 4
    ids = [s["id"] for s in queue.values()]
    co = await people("co", role="contributor")
    assert (
        await co.post("/api/suggestions/accept-allergens", json={"ids": ids})
    ).status_code == 403
    r = await mo.post("/api/suggestions/accept-allergens", json={"ids": ids})
    assert r.json() == {"done": 4, "skipped": 0}
    again = await mo.post("/api/suggestions/accept-allergens", json={"ids": ids})
    assert again.json() == {"done": 0, "skipped": 4}
    shrimp = (await mo.get(f"/api/ingredients/{await _id(adb, 'Shrimp')}")).json()
    assert [a["key"] for a in shrimp["allergens"]] == ["crustaceans"]
    assert await _queue(mo) == {}
