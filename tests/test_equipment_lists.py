"""Your equipment (routers/equipment_lists.py): lists of what you have and
want, built as the larder is (*Ray, 2026-11-16*), and tested as it is."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

API = "/api/equipment-lists"


async def _list(c, name="Kitchen"):
    r = await c.post(f"{API}/lists", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _item(c, list_id, name, **more):
    r = await c.post(f"{API}/lists/{list_id}/items", json={"name": name, **more})
    assert r.status_code == 201, r.text
    return r.json()


async def _thing(adb, name: str) -> str:
    return str(await adb.scalar(text("SELECT id FROM equipment WHERE name = :n"), {"n": name}))


async def _mine(c) -> dict:
    r = await c.get(API)
    assert r.status_code == 200, r.text
    return r.json()


async def test_lists_and_items_are_their_owners(people, client) -> None:
    ann, bo = await people("ann"), await people("bo")
    kitchen = await _list(ann, "  The   cabin ")
    await _item(ann, kitchen, "Grandpa's thing for eggs")
    mine = await _mine(ann)
    assert [lst["name"] for lst in mine["lists"]] == ["The cabin"]
    assert [i["name"] for i in mine["lists"][0]["items"]] == ["Grandpa's thing for eggs"]
    assert (await _mine(bo))["lists"] == []
    assert (await client.get(API)).status_code == 401
    assert (await bo.post(f"{API}/lists/{kitchen}/items", json={"name": "x"})).status_code == 404
    assert (await bo.delete(f"{API}/lists/{kitchen}")).status_code == 404
    assert (await ann.post(f"{API}/lists", json={"name": "   "})).status_code == 422
    assert (await ann.post(f"{API}/lists/{kitchen}/items", json={"name": " "})).status_code == 422


async def test_an_item_is_matched_by_name_and_never_adds_to_the_list(people, adb) -> None:
    ann = await people("ann")
    kitchen = await _list(ann)
    assert (await _item(ann, kitchen, "stand mixer"))["equipment"] == "Stand mixer"
    # Another name for a thing, and a thing with its size beside it.
    assert (await _item(ann, kitchen, "Ice cream machine"))["equipment"] == "Ice cream maker"
    sized = await _item(ann, kitchen, "9-inch springform pan")
    assert (sized["name"], sized["equipment"]) == ("9-inch springform pan", "Springform pan")
    # What nothing matches stays as typed, and makes no piece of equipment.
    before = await adb.scalar(text("SELECT count(*) FROM equipment"))
    odd = await _item(ann, kitchen, "Nana's cauldron")
    assert (odd["equipment_id"], odd["equipment"]) == (None, None)
    assert await adb.scalar(text("SELECT count(*) FROM equipment")) == before
    # Chosen by hand, cleared, and matched from its name again.
    oven = await _thing(adb, "Dutch oven")
    chosen = await ann.patch(f"{API}/items/{odd['id']}", json={"equipment_id": oven})
    assert chosen.json()["equipment"] == "Dutch oven"
    cleared = await ann.patch(f"{API}/items/{odd['id']}", json={"equipment_id": "none"})
    assert cleared.json()["equipment_id"] is None
    renamed = await ann.patch(
        f"{API}/items/{odd['id']}", json={"name": "Nana's wok", "equipment_id": "match"}
    )
    assert renamed.json()["equipment_id"] is None
    again = await ann.patch(
        f"{API}/items/{odd['id']}", json={"name": "Wok", "equipment_id": "match"}
    )
    assert (again.json()["name"], again.json()["equipment"]) == ("Wok", "Wok")
    gone = "00000000-0000-0000-0000-000000000000"
    assert (
        await ann.patch(f"{API}/items/{odd['id']}", json={"equipment_id": gone})
    ).status_code == 422


async def test_have_and_want_and_moving(people, adb) -> None:
    ann = await people("ann")
    kitchen, cabin = await _list(ann, "Kitchen"), await _list(ann, "Cabin")
    wok = await _item(ann, kitchen, "Wok")
    assert wok["state"] == "have" and (await _mine(ann))["counted"] == 1
    # Wanted, it stays on the list and doesn't count as had.
    wanted = await ann.patch(f"{API}/items/{wok['id']}", json={"state": "want"})
    assert wanted.json()["state"] == "want"
    mine = await _mine(ann)
    assert mine["counted"] == 0 and [i["name"] for i in mine["lists"][0]["items"]] == ["Wok"]
    # Added as wanted, and what matches nothing never counts.
    assert (await _item(ann, kitchen, "Ice cream maker", state="want"))["state"] == "want"
    await _item(ann, kitchen, "Nana's cauldron")
    assert (await _mine(ann))["counted"] == 0
    await ann.patch(f"{API}/items/{wok['id']}", json={"state": "have"})
    assert (await _mine(ann))["counted"] == 1
    # A larder's states aren't equipment's.
    for state in ("low", "out", "gone"):
        refused = await ann.patch(f"{API}/items/{wok['id']}", json={"state": state})
        assert refused.status_code == 422, state
    moved = await ann.patch(f"{API}/items/{wok['id']}", json={"list_id": cabin})
    assert moved.json()["list_id"] == cabin
    bo = await people("bo")
    theirs = await _list(bo, "Theirs")
    assert (
        await ann.patch(f"{API}/items/{wok['id']}", json={"list_id": theirs})
    ).status_code == 404
    assert (await ann.delete(f"{API}/items/{wok['id']}")).status_code == 204
    assert (await ann.delete(f"{API}/lists/{kitchen}")).status_code == 204
    assert [lst["name"] for lst in (await _mine(ann))["lists"]] == ["Cabin"]


async def test_a_thing_a_hidden_recipe_brought_is_its_owners_alone(people, adb) -> None:
    """One typed into a family's collection isn't in the equipment list:
    it's matched for whoever can see that recipe, and for nobody else."""
    ann, bo = await people("ann"), await people("bo")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    made = await ann.post(
        f"/api/sources/{box}/recipes",
        json={"title": "Nana's", "ingredients": ["eggs"], "equipment": ["moonbeam press"]},
    )
    assert made.status_code == 201, made.text
    press = await _thing(adb, "Moonbeam press")
    hers = await _item(ann, await _list(ann), "Moonbeam press")
    assert hers["equipment_id"] == press
    his_list = await _list(bo)
    his = await _item(bo, his_list, "Moonbeam press")
    assert (his["equipment_id"], his["equipment"]) == (None, None)
    # Not linked and then hidden: not linked, so it can't count for him
    # later, should he come to see it.
    linked = text("SELECT equipment_id FROM equipment_list_items WHERE id = :i")
    assert await adb.scalar(linked, {"i": his["id"]}) is None
    again = await bo.patch(f"{API}/items/{his['id']}", json={"equipment_id": "match"})
    assert again.json()["equipment_id"] is None
    assert await adb.scalar(linked, {"i": his["id"]}) is None
    refused = await bo.patch(f"{API}/items/{his['id']}", json={"equipment_id": press})
    assert refused.status_code == 422
    # Put there another way, it still isn't named to him, and doesn't count.
    await adb.execute(
        text("UPDATE equipment_list_items SET equipment_id = :e WHERE id = :i"),
        {"e": press, "i": his["id"]},
    )
    mine = await _mine(bo)
    assert mine["counted"] == 0
    assert (mine["lists"][0]["items"][0]["equipment_id"], "Moonbeam" in str(mine)) == (None, True)
    assert mine["lists"][0]["items"][0]["equipment"] is None
    # The thing gone from the catalog, her item stays under her name for it.
    await adb.execute(text("DELETE FROM recipes WHERE id = :r"), {"r": made.json()["id"]})
    await adb.execute(text("DELETE FROM equipment WHERE id = :e"), {"e": press})
    [kept] = (await _mine(ann))["lists"][0]["items"]
    assert (kept["name"], kept["equipment_id"]) == ("Moonbeam press", None)


async def test_merging_equipment_keeps_list_items(people, adb) -> None:
    ann, mo = await people("ann"), await people("mo", role="moderator")
    kept = (await mo.post("/api/equipment", json={"name": "Egg coddler"})).json()["id"]
    gone = (await mo.post("/api/equipment", json={"name": "Coddling cup"})).json()["id"]
    item = await _item(ann, await _list(ann), "Coddling cup")
    assert item["equipment"] == "Coddling cup"
    r = await mo.post(f"/api/equipment/{gone}/merge", json={"into": kept})
    assert r.status_code == 200, r.text
    [after] = (await _mine(ann))["lists"][0]["items"]
    assert (after["name"], after["equipment"], after["equipment_id"]) == (
        "Coddling cup",
        "Egg coddler",
        kept,
    )


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
    kitchen = await _list(ann, "Family kitchen")
    await _item(ann, kitchen, "Wok")
    # Shared with nobody yet: nobody else sees it.
    assert (await _mine(bob))["lists"] == []
    r = await ann.put(f"{API}/lists/{kitchen}/groups", json={"groups": [group]})
    assert r.status_code == 200 and [g["id"] for g in r.json()["shared_with"]] == [group]
    theirs = await _mine(bob)
    [seen] = theirs["lists"]
    assert (seen["name"], seen["mine"], seen["editable"], seen["owner_name"]) == (
        "Family kitchen",
        False,
        False,
        "ann",
    )
    # What's shared with him counts as his to cook with.
    assert theirs["counted"] == 1
    assert (await _mine(dee))["lists"] == []
    # A viewer can't change it; an editor can; only the owner renames or shares.
    assert (
        await bob.post(f"{API}/lists/{kitchen}/items", json={"name": "Blender"})
    ).status_code == 403
    assert (
        await cy.post(f"{API}/lists/{kitchen}/items", json={"name": "Blender"})
    ).status_code == 201
    wok = next(i for i in (await _mine(cy))["lists"][0]["items"] if i["name"] == "Wok")
    assert (await cy.patch(f"{API}/items/{wok['id']}", json={"state": "want"})).status_code == 200
    assert (await cy.patch(f"{API}/lists/{kitchen}", json={"name": "Mine now"})).status_code == 403
    assert (await cy.put(f"{API}/lists/{kitchen}/groups", json={"groups": []})).status_code == 403
    assert (await cy.delete(f"{API}/lists/{kitchen}")).status_code == 403
    assert (await dee.patch(f"{API}/items/{wok['id']}", json={"state": "have"})).status_code == 404
    assert (await dee.delete(f"{API}/items/{wok['id']}")).status_code == 404
    # Only a group she's in.
    elsewhere = await _group_of(dee)
    assert (
        await ann.put(f"{API}/lists/{kitchen}/groups", json={"groups": [elsewhere]})
    ).status_code == 404
    # Unshared, it's gone for them again.
    await ann.put(f"{API}/lists/{kitchen}/groups", json={"groups": []})
    assert (await _mine(cy))["lists"] == []


async def test_moving_needs_both_lists_changeable(people, adb) -> None:
    ann, cy = await people("ann"), await people("cy")
    group = await _group_of(ann, (cy, "view"))
    shared = await _list(ann, "Shared")
    await ann.put(f"{API}/lists/{shared}/groups", json={"groups": [group]})
    own = await _list(cy, "Cy's")
    item = await _item(cy, own, "Wok")
    moved = await cy.patch(f"{API}/items/{item['id']}", json={"list_id": shared})
    assert moved.status_code == 403


async def test_leaving_a_group_stops_sharing_with_it(people, adb) -> None:
    ann, bob = await people("ann"), await people("bob")
    group = await _group_of(ann, (bob, "edit"))
    his = await _list(bob, "Bob's van")
    await bob.put(f"{API}/lists/{his}/groups", json={"groups": [group]})
    assert [lst["name"] for lst in (await _mine(ann))["lists"]] == ["Bob's van"]
    bob_id = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'bob'"))
    assert (await bob.delete(f"/api/groups/{group}/members/{bob_id}")).status_code == 204
    assert (await _mine(ann))["lists"] == []
    assert await adb.scalar(text("SELECT count(*) FROM equipment_list_groups")) == 0
    # It's still his.
    assert [lst["name"] for lst in (await _mine(bob))["lists"]] == ["Bob's van"]


async def test_a_person_and_a_list_hold_so_much(people, adb, monkeypatch) -> None:
    from openlarder.routers import equipment_lists

    ann, cy = await people("ann"), await people("cy")
    monkeypatch.setattr(equipment_lists, "MAX_LISTS", 2)
    monkeypatch.setattr(equipment_lists, "MAX_ITEMS", 2)
    kitchen = await _list(ann, "Kitchen")
    cabin = await _list(ann, "Cabin")
    full = await ann.post(f"{API}/lists", json={"name": "Van"})
    assert full.status_code == 409 and "2 lists" in full.json()["detail"]
    # Counted against the list's owner, whoever adds it.
    group = await _group_of(ann, (cy, "edit"))
    await ann.put(f"{API}/lists/{cabin}/groups", json={"groups": [group]})
    await _item(ann, kitchen, "Wok")
    await _item(cy, cabin, "Blender")
    for who, where in ((ann, kitchen), (cy, cabin)):
        over = await who.post(f"{API}/lists/{where}/items", json={"name": "Whisk"})
        assert over.status_code == 409 and "2 things" in over.json()["detail"]
    assert (await cy.post(f"{API}/lists", json={"name": "Cy's"})).status_code == 201


async def test_the_database_holds_only_have_and_want_and_a_name(people, adb) -> None:
    """Whatever writes a row: a larder's states aren't equipment's, and a
    list and a thing each have a name."""
    ann = await people("ann")
    kitchen = await _list(ann)
    insert = text("INSERT INTO equipment_list_items (list_id, name, state) VALUES (:l, :n, :s)")
    for name, state in (("Wok", "low"), ("Wok", "out"), ("Wok", ""), ("", "have")):
        with pytest.raises(IntegrityError):
            async with adb.begin_nested():
                await adb.execute(insert, {"l": kitchen, "n": name, "s": state})
    for state in ("have", "want"):
        async with adb.begin_nested():
            await adb.execute(insert, {"l": kitchen, "n": "Wok", "s": state})
    with pytest.raises(IntegrityError):
        async with adb.begin_nested():
            await adb.execute(
                text(
                    "INSERT INTO equipment_lists (owner_id, name)"
                    " SELECT owner_id, '' FROM equipment_lists WHERE id = :l"
                ),
                {"l": kitchen},
            )
