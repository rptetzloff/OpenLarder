"""Cooking a recipe for a diet (diets.py): the lines whose ingredients
record an allergen the diet avoids, and the swaps recorded for them."""

from sqlalchemy import text


async def _recipe(mo, adb, book: str, lines: list[str]) -> str:
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": f"Dish {len(lines)}",
            "editions": [{"edition_id": edition, "page": "1"}],
            "ingredients": lines,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _id(adb, name: str) -> str:
    return str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": name}))


def _line(x: dict) -> tuple[str, list[str], list[str]]:
    return (
        x["ingredient"]["name"],
        [f["key"] for f in x["found"]],
        [s["use"]["name"] for s in x["swaps"]],
    )


async def _diets(client) -> dict[str, dict]:
    return {d["name"]: d for d in (await client.get("/api/diets")).json()}


async def test_diets_say_what_they_avoid(client) -> None:
    diets = await _diets(client)
    assert diets["Dairy-Free"]["avoids"] == ["milk"]
    assert diets["Gluten-Free"]["avoids"] == ["wheat", "gluten"]
    assert diets["Vegan"]["avoids"] == ["milk", "egg", "fish", "crustaceans", "molluscs"]
    assert diets["Paleo"]["avoids"] == []
    # A diet, for tags and swaps; meat isn't an allergen.
    assert diets["Pescetarian"]["avoids"] == []


async def test_a_recipe_for_a_diet(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty"})).json()["id"]
    recipe = await _recipe(mo, adb, book, ["Unsalted Butter", "Flour", "Coconut Oil", "Sugar"])
    await _recipe(mo, adb, book, ["Butter", "Margarine", "Ghee", "Rice Flour", "Olive Oil"])
    ids = {
        n: await _id(adb, n)
        for n in ("Butter", "Unsalted Butter", "Flour", "Coconut Oil", "Margarine", "Ghee")
    }
    ids["Rice Flour"], ids["Olive Oil"] = await _id(adb, "Rice Flour"), await _id(adb, "Olive Oil")
    await mo.put(
        f"/api/ingredients/{ids['Unsalted Butter']}/parent", json={"parent": ids["Butter"]}
    )
    for name, statuses in (
        ("Butter", {"milk": "contains"}),
        ("Flour", {"wheat": "contains", "gluten": "contains"}),
        ("Margarine", {"milk": "may_contain"}),
    ):
        await mo.put(f"/api/ingredients/{ids[name]}/allergens", json={"statuses": statuses})
    diets = await _diets(client)

    async def swap(instead: str, use: str, diet: str | None) -> None:
        r = await mo.post(
            "/api/substitutions",
            json={
                "instead_of": {"ingredient_id": ids[instead]},
                "use": {"ingredient_id": ids[use]},
                "diet_id": diets[diet]["id"] if diet else None,
            },
        )
        assert r.status_code in (200, 201), r.text

    # Recorded for Butter, the broader one; for Vegan, which avoids milk too.
    await swap("Butter", "Coconut Oil", "Vegan")
    # Margarine may contain milk itself; Ghee's swap is for no diet; Olive
    # Oil's is for a diet that doesn't avoid milk.
    await swap("Butter", "Margarine", "Dairy-Free")
    await swap("Butter", "Ghee", None)
    await swap("Butter", "Olive Oil", "Paleo")
    await swap("Flour", "Rice Flour", "Gluten-Free")

    got = (await client.get(f"/api/recipes/{recipe}/diets/{diets['Dairy-Free']['id']}")).json()
    assert "unverified" in got["notice"]
    assert [_line(x) for x in got["lines"]] == [("Unsalted Butter", ["milk"], ["Coconut Oil"])]

    got = (await client.get(f"/api/recipes/{recipe}/diets/{diets['Gluten-Free']['id']}")).json()
    assert [_line(x) for x in got["lines"]] == [("Flour", ["wheat", "gluten"], ["Rice Flour"])]
    # A diet that avoids nothing finds nothing.
    got = (await client.get(f"/api/recipes/{recipe}/diets/{diets['Paleo']['id']}")).json()
    assert got["lines"] == []


async def test_moderators_say_what_a_diet_avoids(people, client) -> None:
    mo, co = await people("mo", role="moderator"), await people("co", role="contributor")
    paleo = (await _diets(client))["Paleo"]["id"]
    body = {"allergens": ["milk", "wheat"]}
    assert (await co.put(f"/api/diets/{paleo}/allergens", json=body)).status_code == 403
    r = await mo.put(f"/api/diets/{paleo}/allergens", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["avoids"] == ["milk", "wheat"]
    bad = await mo.put(f"/api/diets/{paleo}/allergens", json={"allergens": ["meat"]})
    assert bad.status_code == 422
    r = await mo.put(f"/api/diets/{paleo}/allergens", json={"allergens": []})
    assert r.json()["avoids"] == []


async def test_a_private_stand_in_is_never_offered(people, client, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty"})).json()["id"]
    recipe = await _recipe(mo, adb, book, ["Butter"])
    butter = await _id(adb, "Butter")
    await mo.put(f"/api/ingredients/{butter}/allergens", json={"statuses": {"milk": "contains"}})
    box = (
        await ann.post("/api/sources/family", json={"title": "Gran's Box", "acknowledged": True})
    ).json()["id"]
    fudge = (await ann.post(f"/api/sources/{box}/recipes", json={"title": "Gran's Spread"})).json()[
        "id"
    ]
    dairy_free = (await _diets(client))["Dairy-Free"]["id"]
    await adb.execute(
        text(
            "INSERT INTO substitutions (from_ingredient_id, to_recipe_id, diet_tag_id, diet_kind)"
            " VALUES (:b, :r, :d, 'diet')"
        ),
        {"b": butter, "r": fudge, "d": dairy_free},
    )
    await adb.commit()
    for who, sees in ((client, False), (mo, False), (ann, True)):
        got = (await who.get(f"/api/recipes/{recipe}/diets/{dairy_free}")).json()
        [line] = got["lines"]
        assert bool(line["swaps"]) is sees
        assert ("Gran" in str(got)) is sees
