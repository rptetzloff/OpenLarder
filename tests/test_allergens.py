"""Allergens on ingredients (allergens.py): recorded by moderators,
inherited down the hierarchy, and listed on recipes only as what their
ingredients contain or may contain."""

from sqlalchemy import text

from openlarder import allergens, dumps


async def _recipe(mo, adb, lines: list[str]) -> str:
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty"})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Cheese Board",
            "editions": [{"edition_id": edition, "page": "12"}],
            "ingredients": lines,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _id(adb, name: str) -> str:
    return str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": name}))


async def test_the_list_comes_with_its_notice(client) -> None:
    got = (await client.get("/api/allergens")).json()
    keys = [a["key"] for a in got["allergens"]]
    assert keys[:3] == ["milk", "egg", "fish"] and "sesame" in keys and len(keys) == 15
    assert got["notice"] == allergens.NOTICE and "unverified" in got["notice"]


async def test_recorded_inherited_and_overridden(people, adb) -> None:
    mo = await people("mo", role="moderator")
    recipe = await _recipe(mo, adb, ["Cheese", "Cheddar", "Vegan Cheese", "Oats", "Apple"])
    cheese, cheddar, vegan, oats = [
        await _id(adb, n) for n in ("Cheese", "Cheddar", "Vegan Cheese", "Oats")
    ]
    for child in (cheddar, vegan):
        r = await mo.put(f"/api/ingredients/{child}/parent", json={"parent": cheese})
        assert r.status_code == 200, r.text

    r = await mo.put(
        f"/api/ingredients/{cheese}/allergens", json={"statuses": {"milk": "contains"}}
    )
    assert r.status_code == 200, r.text
    assert r.json() == [
        {"key": "milk", "label": "Milk", "status": "contains", "inherited": False,
         "inherited_from": None}
    ]  # fmt: skip
    await mo.put(f"/api/ingredients/{vegan}/allergens", json={"statuses": {"milk": "free"}})
    await mo.put(f"/api/ingredients/{oats}/allergens", json={"statuses": {"gluten": "may_contain"}})

    got = (await mo.get(f"/api/ingredients/{cheddar}")).json()["allergens"]
    assert got == [
        {"key": "milk", "label": "Milk", "status": "contains", "inherited": True,
         "inherited_from": {"id": cheese, "name": "Cheese"}}
    ]  # fmt: skip
    got = (await mo.get(f"/api/ingredients/{vegan}")).json()["allergens"]
    assert [(a["key"], a["status"], a["inherited"]) for a in got] == [("milk", "free", False)]

    # The recipe: what's contained or maybe contained, never what isn't.
    got = (await mo.get(f"/api/recipes/{recipe}")).json()["allergens"]
    assert got == [
        {"key": "milk", "label": "Milk", "status": "contains", "ingredients": [
            {"id": cheese, "name": "Cheese", "status": "contains"},
            {"id": cheddar, "name": "Cheddar", "status": "contains"},
        ]},
        {"key": "gluten", "label": "Gluten (wheat, barley, rye)", "status": "may_contain",
         "ingredients": [
            {"id": oats, "name": "Oats", "status": "may_contain"},
        ]},
    ]  # fmt: skip

    # Leaving one out records nothing, and inherits again.
    await mo.put(f"/api/ingredients/{vegan}/allergens", json={"statuses": {}})
    got = (await mo.get(f"/api/ingredients/{vegan}")).json()["allergens"]
    assert [(a["key"], a["status"], a["inherited"]) for a in got] == [("milk", "contains", True)]


async def test_only_moderators_record_and_only_known_ones(people, adb) -> None:
    mo, co = await people("mo", role="moderator"), await people("co", role="contributor")
    await _recipe(mo, adb, ["Peanut"])
    peanut = await _id(adb, "Peanut")
    r = await co.put(
        f"/api/ingredients/{peanut}/allergens", json={"statuses": {"peanuts": "contains"}}
    )
    assert r.status_code == 403
    r = await mo.put(
        f"/api/ingredients/{peanut}/allergens", json={"statuses": {"nuts": "contains"}}
    )
    assert r.status_code == 422 and "nuts" in r.json()["detail"]
    r = await mo.put(f"/api/ingredients/{peanut}/allergens", json={"statuses": {"peanuts": "yes"}})
    assert r.status_code == 422


async def test_history_revert_merge_and_dumps(people, adb) -> None:
    mo = await people("mo", role="moderator")
    await _recipe(mo, adb, ["Butter", "Unsalted Butter", "Tahini"])
    butter, unsalted, tahini = [await _id(adb, n) for n in ("Butter", "Unsalted Butter", "Tahini")]
    await mo.put(f"/api/ingredients/{tahini}/allergens", json={"statuses": {"sesame": "contains"}})
    history = (await mo.get(f"/api/ingredients/{tahini}/history")).json()
    [change] = [c for c in history if any(e["what"] == "allergen" for e in c["entries"])]
    r = await mo.post(f"/api/changes/{change['id']}/revert")
    assert r.status_code == 200, r.text
    assert (await mo.get(f"/api/ingredients/{tahini}")).json()["allergens"] == []

    # A merge keeps what's recorded, the kept ingredient's first.
    await mo.put(
        f"/api/ingredients/{unsalted}/allergens",
        json={"statuses": {"milk": "contains", "sulphites": "may_contain"}},
    )
    await mo.put(f"/api/ingredients/{butter}/allergens", json={"statuses": {"milk": "may_contain"}})
    r = await mo.post(f"/api/ingredients/{unsalted}/merge", json={"into": butter})
    assert r.status_code == 200, r.text
    got = (await mo.get(f"/api/ingredients/{butter}")).json()["allergens"]
    assert [(a["key"], a["status"]) for a in got] == [
        ("milk", "may_contain"),
        ("sulphites", "may_contain"),
    ]

    rows = await dumps.read(adb)
    assert [a["key"] for a in rows["allergens"]][:2] == ["milk", "egg"]
    assert {(r["ingredient_id"], r["allergen"]) for r in rows["ingredient_allergens"]} == {
        (butter, "milk"),
        (butter, "sulphites"),
    }
