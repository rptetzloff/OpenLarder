"""Saved recipes (routers/saved.py): want to cook, cooked, shared, searched."""

from sqlalchemy import text


async def _book(mo, adb, title):
    book = (await mo.post("/api/sources/manual", json={"title": title})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    return book, edition


async def _recipe(mo, book, edition, title, page="12"):
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={"title": title, "editions": [{"edition_id": edition, "page": page}]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _user_id(adb, name):
    return str(await adb.scalar(text("SELECT id FROM users WHERE display_name = :n"), {"n": name}))


def _titles(saved: dict) -> list[tuple[str, str]]:
    return [(r["title"], r["state"]) for r in saved["recipes"]]


async def test_saved_wanted_cooked_and_taken_off(people, client, adb) -> None:
    mo, ann, bo = await people("mo", role="moderator"), await people("ann"), await people("bo")
    book, edition = await _book(mo, adb, "Plenty")
    soup = await _recipe(mo, book, edition, "Barley Soup")
    cake = await _recipe(mo, book, edition, "Apple Cake", "40")

    assert (await ann.get(f"/api/saved/{soup}")).json() == {
        "recipe_id": soup,
        "state": None,
        "others": [],
    }
    assert (await ann.put(f"/api/saved/{soup}", json={})).json()["state"] == "want"
    assert (await ann.put(f"/api/saved/{cake}", json={"state": "cooked"})).json()["state"] == (
        "cooked"
    )
    saved = (await ann.get("/api/saved")).json()
    assert _titles(saved) == [("Apple Cake", "cooked"), ("Barley Soup", "want")]
    # A card says where it is.
    assert (saved["recipes"][0]["source_title"], saved["recipes"][0]["pages"]) == ("Plenty", ["40"])

    # Nobody else's, and nothing signed out.
    assert (await bo.get("/api/saved")).json()["recipes"] == []
    assert (await bo.get(f"/api/saved/{soup}")).json()["state"] is None
    assert (await client.get("/api/saved")).status_code == 401
    assert (await client.put(f"/api/saved/{soup}", json={})).status_code == 401

    # Cooked, then off.
    assert (await ann.put(f"/api/saved/{soup}", json={"state": "cooked"})).json()["state"] == (
        "cooked"
    )
    assert (await ann.put(f"/api/saved/{soup}", json={"state": "eaten"})).status_code == 422
    assert (await ann.delete(f"/api/saved/{soup}")).status_code == 204
    assert _titles((await ann.get("/api/saved")).json()) == [("Apple Cake", "cooked")]

    # Removing the recipe takes it off.
    await adb.execute(text("DELETE FROM recipes WHERE id = :r"), {"r": cake})
    assert (await ann.get("/api/saved")).json()["recipes"] == []


async def test_a_private_recipe_is_only_saved_by_who_sees_it(people, adb) -> None:
    from test_larder import _group_of

    ann, bo = await people("ann"), await people("bo")
    box = (
        await ann.post("/api/sources/family", json={"title": "Gran's Box", "acknowledged": True})
    ).json()["id"]
    fudge = (
        await ann.post(f"/api/sources/{box}/recipes", json={"title": "Fudge", "ingredients": []})
    ).json()["id"]
    assert (await bo.put(f"/api/saved/{fudge}", json={})).status_code == 404
    await ann.put(f"/api/saved/{fudge}", json={})

    # Ann shares her list with Bo, but not the collection: Bo doesn't see Fudge.
    group = await _group_of(ann, (bo, "edit"))
    await ann.put("/api/saved/groups", json={"groups": [group]})
    [shared] = (await bo.get("/api/saved")).json()["shared"]
    assert shared["owner_name"] == "ann" and shared["recipes"] == []
    assert (await bo.get(f"/api/saved/{fudge}")).json()["others"][0]["state"] is None
    found = (await bo.get("/api/search", params={"saved": True})).json()
    assert found["total"] == 0


async def test_saved_recipes_are_shared_with_a_group(people, adb) -> None:
    from test_larder import _group_of

    mo = await people("mo", role="moderator")
    ann, bob, cy, dee = (
        await people("ann"),
        await people("bob"),
        await people("cy"),
        await people("dee"),
    )
    ann_id = await _user_id(adb, "ann")
    group = await _group_of(ann, (bob, "view"), (cy, "edit"))
    book, edition = await _book(mo, adb, "Plenty")
    soup = await _recipe(mo, book, edition, "Barley Soup")
    cake = await _recipe(mo, book, edition, "Apple Cake")
    await ann.put(f"/api/saved/{soup}", json={})

    assert (await bob.get("/api/saved")).json()["shared"] == []
    stranger = await _group_of(dee)
    assert (await ann.put("/api/saved/groups", json={"groups": [stranger]})).status_code == 404
    r = await ann.put("/api/saved/groups", json={"groups": [group]})
    assert r.status_code == 200 and [g["id"] for g in r.json()["shared_with"]] == [group]

    [seen] = (await bob.get("/api/saved")).json()["shared"]
    assert (seen["owner_name"], seen["editable"], _titles(seen)) == (
        "ann",
        False,
        [("Barley Soup", "want")],
    )
    assert (await dee.get("/api/saved")).json()["shared"] == []
    [other] = (await bob.get(f"/api/saved/{soup}")).json()["others"]
    assert (other["owner_name"], other["state"]) == ("ann", "want")

    # A viewer can't change it; an editor can; a stranger can't see it's there.
    whose = {"owner": ann_id}
    assert (await bob.put(f"/api/saved/{cake}", params=whose, json={})).status_code == 403
    assert (await bob.delete(f"/api/saved/{soup}", params=whose)).status_code == 403
    assert (await dee.put(f"/api/saved/{cake}", params=whose, json={})).status_code == 404
    assert (await cy.put(f"/api/saved/{cake}", params=whose, json={})).status_code == 200
    cooked = await cy.put(f"/api/saved/{soup}", params=whose, json={"state": "cooked"})
    assert cooked.json()["others"][0]["state"] == "cooked"
    assert _titles((await ann.get("/api/saved")).json()) == [
        ("Apple Cake", "want"),
        ("Barley Soup", "cooked"),
    ]
    assert (await cy.get("/api/saved")).json()["recipes"] == []

    # Unshared, it's gone from theirs.
    await ann.put("/api/saved/groups", json={"groups": []})
    assert (await bob.get("/api/saved")).json()["shared"] == []


async def test_search_keeps_to_saved_recipes(people, client, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    book, edition = await _book(mo, adb, "Plenty")
    green = await _recipe(mo, book, edition, "Green Shakshuka")
    await _recipe(mo, book, edition, "Red Shakshuka")
    await ann.put(f"/api/saved/{green}", json={})

    found = (await ann.get("/api/search", params={"q": "shakshuka", "saved": True})).json()
    assert [r["title"] for r in found["recipes"]] == ["Green Shakshuka"]
    # On its own, it lists them.
    alone = (await ann.get("/api/search", params={"saved": True})).json()
    assert [r["title"] for r in alone["recipes"]] == ["Green Shakshuka"]
    assert (await ann.get("/api/search", params={"q": "shakshuka"})).json()["total"] == 2
    assert (await client.get("/api/search", params={"saved": True})).status_code == 401


async def test_leaving_and_deleting_clear_up(people, adb) -> None:
    from test_larder import _group_of

    mo, ann, bob = await people("mo", role="moderator"), await people("ann"), await people("bob")
    bob_id = await _user_id(adb, "bob")
    book, edition = await _book(mo, adb, "Plenty")
    soup = await _recipe(mo, book, edition, "Barley Soup")
    group = await _group_of(ann, (bob, "edit"))
    await bob.put(f"/api/saved/{soup}", json={})
    await bob.put("/api/saved/groups", json={"groups": [group]})
    assert len((await ann.get("/api/saved")).json()["shared"]) == 1

    assert (await bob.delete(f"/api/groups/{group}/members/{bob_id}")).status_code == 204
    assert (await ann.get("/api/saved")).json()["shared"] == []
    assert await adb.scalar(text("SELECT count(*) FROM saved_groups")) == 0

    assert (await bob.post("/api/account/delete", json={"confirm": "bob"})).status_code == 204
    assert await adb.scalar(text("SELECT count(*) FROM saved_recipes")) == 0
