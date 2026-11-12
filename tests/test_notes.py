"""Notes on recipes (routers/notes.py): yours alone, or shared with groups."""

from sqlalchemy import text


async def _recipe(mo, adb, title="Barley Soup"):
    book = (await mo.post("/api/sources/manual", json={"title": f"Book of {title}"})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={"title": title, "editions": [{"edition_id": edition, "page": "12"}]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _user_id(adb, name):
    return str(await adb.scalar(text("SELECT id FROM users WHERE display_name = :n"), {"n": name}))


async def test_a_note_is_its_writers_alone(people, client, adb) -> None:
    mo, ad = await people("mo", role="moderator"), await people("ad", role="admin")
    ann, bo = await people("ann"), await people("bo")
    soup = await _recipe(mo, adb)
    url = f"/api/recipes/{soup}/notes"

    assert (await ann.get(url)).json() == {"mine": None, "groups": [], "others": []}
    r = await ann.put(url, json={"body": "  Double the barley.\nLess salt.  "})
    assert r.status_code == 200, r.text
    mine = r.json()["mine"]
    assert (mine["body"], mine["shared_with"]) == ("Double the barley.\nLess salt.", [])

    # Nobody else reads it: not another cook, a moderator or an administrator.
    for other in (bo, mo, ad):
        assert (await other.get(url)).json() == {"mine": None, "groups": [], "others": []}
        assert (await other.get("/api/notes")).json()["notes"] == []
    assert (await client.get(url)).status_code == 401
    assert (await client.get("/api/notes")).status_code == 401
    assert (await client.put(url, json={"body": "x"})).status_code == 401

    # One each: Bo's is his own.
    await bo.put(url, json={"body": "Too thick."})
    assert (await ann.get(url)).json()["mine"]["body"] == "Double the barley.\nLess salt."
    assert (await bo.get(url)).json()["mine"]["body"] == "Too thick."

    # Changed, refused when empty or too long, and removed.
    assert (await ann.put(url, json={"body": "Triple it."})).json()["mine"]["body"] == "Triple it."
    assert await adb.scalar(text("SELECT count(*) FROM recipe_notes")) == 2
    assert (await ann.put(url, json={"body": "   "})).status_code == 422
    assert (await ann.put(url, json={"body": "x" * 2001})).status_code == 422
    [listed] = (await ann.get("/api/notes")).json()["notes"]
    assert (listed["title"], listed["body"], listed["mine"]) == ("Barley Soup", "Triple it.", True)
    assert (await ann.delete(url)).status_code == 204
    assert (await ann.get(url)).json()["mine"] is None
    assert (await bo.get(url)).json()["mine"]["body"] == "Too thick."


async def test_a_note_is_shared_with_the_groups_ticked(people, adb) -> None:
    from test_larder import _group_of

    mo = await people("mo", role="moderator")
    ann, bob, cy, dee = (
        await people("ann"),
        await people("bob"),
        await people("cy"),
        await people("dee"),
    )
    family = await _group_of(ann, (bob, "view"))
    friends = await _group_of(ann, (cy, "admin"))
    stranger = await _group_of(dee)
    soup = await _recipe(mo, adb)
    url = f"/api/recipes/{soup}/notes"

    bad = await ann.put(url, json={"body": "Less salt.", "groups": [stranger]})
    assert bad.status_code == 404
    r = await ann.put(url, json={"body": "Less salt.", "groups": [family]})
    assert [g["id"] for g in r.json()["mine"]["shared_with"]] == [family]
    assert sorted(g["id"] for g in r.json()["groups"]) == sorted([family, friends])

    [seen] = (await bob.get(url)).json()["others"]
    assert (seen["author"], seen["body"], [g["id"] for g in seen["through"]]) == (
        "ann",
        "Less salt.",
        [family],
    )
    [listed] = (await bob.get("/api/notes")).json()["notes"]
    assert (listed["author"], listed["mine"], listed["body"]) == ("ann", False, "Less salt.")
    # Not the other group, nor a stranger.
    for other in (cy, dee):
        assert (await other.get(url)).json()["others"] == []
        assert (await other.get("/api/notes")).json()["notes"] == []
    # A reader can't change it, whatever their role in the group: theirs is their own.
    await cy.put(url, json={"body": "Mine."})
    assert (await ann.get(url)).json()["mine"]["body"] == "Less salt."

    # Unticked, it's the writer's alone again.
    await ann.put(url, json={"body": "Less salt.", "groups": []})
    assert (await bob.get(url)).json()["others"] == []


async def test_a_note_on_a_private_recipe_stays_with_who_sees_it(people, adb) -> None:
    from test_larder import _group_of

    ann, bo = await people("ann"), await people("bo")
    box = (
        await ann.post("/api/sources/family", json={"title": "Gran's Box", "acknowledged": True})
    ).json()["id"]
    fudge = (
        await ann.post(f"/api/sources/{box}/recipes", json={"title": "Fudge", "ingredients": []})
    ).json()["id"]
    url = f"/api/recipes/{fudge}/notes"
    assert (await bo.put(url, json={"body": "x"})).status_code == 404
    # Shared with a group Bo is in, on a recipe he can't see: not shown.
    group = await _group_of(ann, (bo, "view"))
    await ann.put(url, json={"body": "The secret is rum.", "groups": [group]})
    assert (await bo.get(url)).status_code == 404
    assert (await bo.get("/api/notes")).json()["notes"] == []


async def test_leaving_and_deleting_clear_up(people, adb) -> None:
    from test_larder import _group_of

    mo, ann, bob = await people("mo", role="moderator"), await people("ann"), await people("bob")
    bob_id = await _user_id(adb, "bob")
    soup = await _recipe(mo, adb)
    url = f"/api/recipes/{soup}/notes"
    group = await _group_of(ann, (bob, "edit"))
    await bob.put(url, json={"body": "More pepper.", "groups": [group]})
    assert len((await ann.get(url)).json()["others"]) == 1

    # Leaving the group stops the sharing; the note is still Bob's.
    assert (await bob.delete(f"/api/groups/{group}/members/{bob_id}")).status_code == 204
    assert (await ann.get(url)).json()["others"] == []
    assert (await bob.get(url)).json()["mine"]["shared_with"] == []

    assert (await bob.post("/api/account/delete", json={"confirm": "bob"})).status_code == 204
    assert await adb.scalar(text("SELECT count(*) FROM recipe_notes")) == 0
