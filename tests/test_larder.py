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


# Sharing with household groups


async def _group_of(ann, *members):
    """Ann's group, with each (client, role) joined."""
    from test_groups import _group, _join

    group = await _group(ann)
    for client, role in members:
        await _join(client, ann, group, role)
    return group


async def test_a_list_is_shared_with_a_group(people, adb) -> None:
    ann, bob, cy, dee = (
        await people("ann"),
        await people("bob"),
        await people("cy"),
        await people("dee"),
    )
    group = await _group_of(ann, (bob, "view"), (cy, "edit"))
    pantry = await _list(ann, "Family pantry")
    await _ingredient(adb, "Butter")
    await _item(ann, pantry, "Butter")
    # Shared with nobody yet: nobody else sees it.
    assert (await bob.get("/api/larder")).json()["lists"] == []
    r = await ann.put(f"/api/larder/lists/{pantry}/groups", json={"groups": [group]})
    assert r.status_code == 200 and [g["id"] for g in r.json()["shared_with"]] == [group]
    [seen] = (await bob.get("/api/larder")).json()["lists"]
    assert (seen["name"], seen["mine"], seen["editable"], seen["owner_name"]) == (
        "Family pantry",
        False,
        False,
        "ann",
    )
    assert (await dee.get("/api/larder")).json()["lists"] == []
    # A viewer can't change it; an editor can; only the owner renames or shares.
    assert (
        await bob.post(f"/api/larder/lists/{pantry}/items", json={"name": "Eggs"})
    ).status_code == 403
    assert (
        await cy.post(f"/api/larder/lists/{pantry}/items", json={"name": "Eggs"})
    ).status_code == 201
    butter = next(
        i
        for i in (await cy.get("/api/larder")).json()["lists"][0]["items"]
        if i["name"] == "Butter"
    )
    assert (
        await cy.patch(f"/api/larder/items/{butter['id']}", json={"state": "low"})
    ).status_code == 200
    assert (
        await cy.patch(f"/api/larder/lists/{pantry}", json={"name": "Mine now"})
    ).status_code == 403
    assert (
        await cy.put(f"/api/larder/lists/{pantry}/groups", json={"groups": []})
    ).status_code == 403
    assert (await cy.delete(f"/api/larder/lists/{pantry}")).status_code == 403
    assert (
        await dee.patch(f"/api/larder/items/{butter['id']}", json={"state": "out"})
    ).status_code == 404
    # Unshared, it's gone for them again.
    await ann.put(f"/api/larder/lists/{pantry}/groups", json={"groups": []})
    assert (await cy.get("/api/larder")).json()["lists"] == []


async def test_only_your_own_groups_and_shared_lists_count_in_search(people, adb) -> None:
    ann, bob, mo = await people("ann"), await people("bob"), await people("mo", role="moderator")
    stranger = await _group_of(bob)
    pantry = await _list(ann)
    r = await ann.put(f"/api/larder/lists/{pantry}/groups", json={"groups": [stranger]})
    assert r.status_code == 404
    group = await _group_of(ann, (bob, "view"))
    await ann.put(f"/api/larder/lists/{pantry}/groups", json={"groups": [group]})
    await _ingredient(adb, "Butter")
    await _item(ann, pantry, "Butter")
    await _recipes(mo, adb, ("Shortbread", ["Butter"]))
    found = (await bob.get("/api/search", params={"larder": "true"})).json()
    assert found["larder_items"] == 1 and [r["title"] for r in found["recipes"]] == ["Shortbread"]


async def test_moving_needs_both_lists_changeable(people, adb) -> None:
    ann, cy = await people("ann"), await people("cy")
    group = await _group_of(ann, (cy, "view"))
    shared = await _list(ann, "Shared")
    await ann.put(f"/api/larder/lists/{shared}/groups", json={"groups": [group]})
    own = await _list(cy, "Cy's")
    item = await _item(cy, own, "Flour")
    moved = await cy.patch(f"/api/larder/items/{item['id']}", json={"list_id": shared})
    assert moved.status_code == 403
