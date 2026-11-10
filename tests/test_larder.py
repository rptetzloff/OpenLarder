"""The personal larder (routers/larder.py) and searching with it."""

from sqlalchemy import text

from openlarder.ingredients import match_key


async def _list(c, name="Pantry"):
    r = await c.post("/api/larder/lists", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _item(c, list_id, name, **more):
    r = await c.post(f"/api/larder/lists/{list_id}/items", json={"name": name, **more})
    assert r.status_code == 201, r.text
    return r.json()


async def _ingredient(adb, name, parent=None):
    return await adb.scalar(
        text(
            "INSERT INTO ingredients (name, match_key, parent_id) VALUES (:n, :k, :p) RETURNING id"
        ),
        {"n": name, "k": match_key(name), "p": parent},
    )


async def test_lists_and_items_are_their_owners(people, client) -> None:
    ann, bo = await people("ann"), await people("bo")
    pantry = await _list(ann, "  Spice   drawer ")
    await _item(ann, pantry, "Grandma's secret blend")
    larder = (await ann.get("/api/larder")).json()
    assert [lst["name"] for lst in larder["lists"]] == ["Spice drawer"]
    assert [i["name"] for i in larder["lists"][0]["items"]] == ["Grandma's secret blend"]
    assert (await bo.get("/api/larder")).json()["lists"] == []
    assert (await client.get("/api/larder")).status_code == 401
    assert (
        await bo.post(f"/api/larder/lists/{pantry}/items", json={"name": "x"})
    ).status_code == 404
    assert (await bo.delete(f"/api/larder/lists/{pantry}")).status_code == 404


async def test_an_item_is_matched_by_name_and_never_makes_an_ingredient(people, adb) -> None:
    ann = await people("ann")
    sauce = await _ingredient(adb, "Hot Sauce")
    await adb.execute(
        text(
            "INSERT INTO ingredient_aliases (ingredient_id, name, match_key)"
            " VALUES (:i, 'Sriracha', :k)"
        ),
        {"i": sauce, "k": match_key("Sriracha")},
    )
    pantry = await _list(ann)
    assert (await _item(ann, pantry, "hot sauce"))["ingredient"] == "Hot Sauce"
    assert (await _item(ann, pantry, "Sriracha"))["ingredient"] == "Hot Sauce"
    odd = await _item(ann, pantry, "Cholula Chipotle")
    assert odd["ingredient_id"] is None
    before = await adb.scalar(text("SELECT count(*) FROM ingredients"))
    await _item(ann, pantry, "Nana's Moonsalt")
    assert await adb.scalar(text("SELECT count(*) FROM ingredients")) == before
    # Chosen by hand, then cleared.
    chosen = await ann.patch(f"/api/larder/items/{odd['id']}", json={"ingredient_id": str(sauce)})
    assert chosen.json()["ingredient"] == "Hot Sauce"
    cleared = await ann.patch(f"/api/larder/items/{odd['id']}", json={"ingredient_id": "none"})
    assert cleared.json()["ingredient_id"] is None


async def test_state_and_moving(people, adb) -> None:
    ann = await people("ann")
    await _ingredient(adb, "Butter")
    fridge, freezer = await _list(ann, "Fridge"), await _list(ann, "Freezer")
    butter = await _item(ann, fridge, "Butter")
    assert (await ann.get("/api/larder")).json()["counted"] == 1
    low = await ann.patch(f"/api/larder/items/{butter['id']}", json={"state": "low"})
    assert low.json()["state"] == "low"
    assert (await ann.get("/api/larder")).json()["counted"] == 1
    await ann.patch(f"/api/larder/items/{butter['id']}", json={"state": "out"})
    assert (await ann.get("/api/larder")).json()["counted"] == 0
    moved = await ann.patch(f"/api/larder/items/{butter['id']}", json={"list_id": freezer})
    assert moved.json()["list_id"] == freezer
    bo = await people("bo")
    theirs = await _list(bo, "Theirs")
    assert (
        await ann.patch(f"/api/larder/items/{butter['id']}", json={"list_id": theirs})
    ).status_code == 404
    assert (
        await ann.patch(f"/api/larder/items/{butter['id']}", json={"state": "gone"})
    ).status_code == 422


async def _recipes(mo, adb, *recipes):
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": []})).json()[
        "id"
    ]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    for title, lines in recipes:
        r = await mo.post(
            f"/api/sources/{book}/recipes",
            json={
                "title": title,
                "editions": [{"edition_id": edition}],
                "ingredients": list(lines),
            },
        )
        assert r.status_code == 201, r.text


async def test_a_larder_item_counts_as_itself_and_whats_above_it(people, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    sauce = await _ingredient(adb, "Hot Sauce")
    await _ingredient(adb, "Chipotle Hot Sauce", sauce)
    await _recipes(
        mo,
        adb,
        ("Wings", ["Hot Sauce"]),
        ("Smoky Wings", ["Chipotle Hot Sauce"]),
        ("Toast", ["Bread"]),
    )
    pantry = await _list(ann)
    item = await _item(
        ann,
        pantry,
        "Cholula Chipotle",
        ingredient_id=str(
            await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Chipotle Hot Sauce'"))
        ),
    )
    found = (await ann.get("/api/search", params={"larder": "true"})).json()
    assert found["larder_items"] == 1
    assert sorted(r["title"] for r in found["recipes"]) == ["Smoky Wings", "Wings"]
    # Plain hot sauce isn't chipotle: only the recipe asking for hot sauce.
    await ann.patch(f"/api/larder/items/{item['id']}", json={"ingredient_id": str(sauce)})
    found = (await ann.get("/api/search", params={"larder": "true"})).json()
    assert [r["title"] for r in found["recipes"]] == ["Wings"]
    # Out doesn't count; running low does.
    await ann.patch(f"/api/larder/items/{item['id']}", json={"state": "out"})
    found = (await ann.get("/api/search", params={"larder": "true"})).json()
    assert (found["larder_items"], found["recipes"]) == (0, [])
    await ann.patch(f"/api/larder/items/{item['id']}", json={"state": "low"})
    assert (await ann.get("/api/search", params={"larder": "true"})).json()["recipes"]


async def test_searching_with_a_larder_needs_signing_in(client, people) -> None:
    assert (await client.get("/api/search", params={"larder": "true"})).status_code == 401
    empty = (await (await people("ann")).get("/api/search", params={"larder": "true"})).json()
    assert (empty["larder_items"], empty["recipes"]) == (0, [])


async def test_merging_an_ingredient_keeps_larder_items(people, adb) -> None:
    ann, mo = await people("ann"), await people("mo", role="moderator")
    kept = await _ingredient(adb, "Coriander")
    gone = await _ingredient(adb, "Cilantro")
    pantry = await _list(ann)
    item = await _item(ann, pantry, "Cilantro")
    assert item["ingredient"] == "Cilantro"
    r = await mo.post(f"/api/ingredients/{gone}/merge", json={"into": str(kept)})
    assert r.status_code == 200, r.text
    [after] = (await ann.get("/api/larder")).json()["lists"][0]["items"]
    assert after["ingredient"] == "Coriander"
