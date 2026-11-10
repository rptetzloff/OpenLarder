"""Undoing a change from the edit history (revert.py)."""

from sqlalchemy import text


async def _book(mo, adb, title="Plenty"):
    book = (await mo.post("/api/sources/manual", json={"title": title, "authors": []})).json()["id"]
    edition = await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    return book, str(edition)


async def _recipe(mo, book, edition, title="Shakshuka", lines=("eggs", "tomatoes")):
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": title,
            "editions": [{"edition_id": edition, "page": "12"}],
            "ingredients": list(lines),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _latest(client, kind, id_):
    return (await client.get(f"/api/{kind}/{id_}/history")).json()[0]


async def _fresh_change(adb):
    """Tests share one transaction; a hand-made row needs its own change."""
    await adb.execute(text("SELECT set_config('openlarder.change', gen_random_uuid()::text, true)"))


async def _edit_title(mo, recipe, edition, title):
    r = await mo.put(
        f"/api/recipes/{recipe}",
        json={
            "title": title,
            "editions": [{"edition_id": edition, "page": "12"}],
            "ingredients": ["eggs", "tomatoes"],
        },
    )
    assert r.status_code == 200, r.text


async def test_an_edit_is_undone_and_the_undo_recorded(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book, edition = await _book(mo, adb)
    recipe = await _recipe(mo, book, edition)
    await _edit_title(mo, recipe, edition, "Green Shakshuka")
    change = await _latest(client, "recipes", recipe)
    r = await mo.post(f"/api/changes/{change['id']}/revert")
    assert r.status_code == 200, r.text
    assert (await client.get(f"/api/recipes/{recipe}")).json()["title"] == "Shakshuka"
    undo = await _latest(client, "recipes", recipe)
    assert undo["by"] == "mo" and undo["via"] == f"revert:{change['id']}"


async def test_an_addition_is_taken_away(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book, edition = await _book(mo, adb)
    recipe = await _recipe(mo, book, edition)
    added = await _latest(client, "recipes", recipe)
    assert (await mo.post(f"/api/changes/{added['id']}/revert")).status_code == 200
    assert (await client.get(f"/api/recipes/{recipe}")).status_code == 404
    left = await adb.scalar(
        text("SELECT count(*) FROM recipe_ingredients WHERE recipe_id = :r"), {"r": recipe}
    )
    assert left == 0


async def test_a_removal_is_put_back_whole(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book, edition = await _book(mo, adb)
    recipe = await _recipe(mo, book, edition)
    before = (await client.get(f"/api/recipes/{recipe}")).json()
    assert (await mo.delete(f"/api/recipes/{recipe}")).status_code == 204
    removed = (await client.get(f"/api/sources/{book}/history")).json()[0]
    assert {e["action"] for e in removed["entries"]} == {"removed"}
    r = await mo.post(f"/api/changes/{removed['id']}/revert")
    assert r.status_code == 200, r.text
    after = (await client.get(f"/api/recipes/{recipe}")).json()
    for key in ("title", "ingredients", "pages"):
        assert after[key] == before[key], key
    assert [o["ingredient"] for line in after["lines"] for o in line["options"]] == [
        o["ingredient"] for line in before["lines"] for o in line["options"]
    ]


async def test_a_later_change_to_the_same_rows_comes_first(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book, edition = await _book(mo, adb)
    recipe = await _recipe(mo, book, edition)
    await _edit_title(mo, recipe, edition, "Two")
    first = await _latest(client, "recipes", recipe)
    await _edit_title(mo, recipe, edition, "Three")
    second = await _latest(client, "recipes", recipe)
    refused = await mo.post(f"/api/changes/{first['id']}/revert")
    assert refused.status_code == 409 and "later change" in refused.json()["detail"]
    assert (await mo.post(f"/api/changes/{second['id']}/revert")).status_code == 200
    # The undo is later than the first change too, so it's still refused;
    # undoing the undo (redoing "Three") is allowed.
    undo = await _latest(client, "recipes", recipe)
    assert (await mo.post(f"/api/changes/{undo['id']}/revert")).status_code == 200
    assert (await client.get(f"/api/recipes/{recipe}")).json()["title"] == "Three"


async def test_only_moderators_and_not_a_private_collection(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    ann = await people("ann")
    book, edition = await _book(mo, adb)
    await _recipe(mo, book, edition)
    change = (await mo.get(f"/api/sources/{book}/history")).json()[0]
    assert (await con.post(f"/api/changes/{change['id']}/revert")).status_code == 403
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    [own] = (await ann.get(f"/api/sources/{box}/history")).json()
    assert (await mo.post(f"/api/changes/{own['id']}/revert")).status_code == 404


async def test_a_removal_from_before_whole_rows_cant_be_put_back(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    await _fresh_change(adb)
    await adb.execute(text("INSERT INTO ingredients (name, match_key) VALUES ('Sumac', 'sumac')"))
    await _fresh_change(adb)
    await adb.execute(text("DELETE FROM ingredients WHERE name = 'Sumac'"))
    # As 0040 recorded removals: without the match key.
    await adb.execute(
        text(
            "UPDATE revisions SET changes = changes - 'match_key'"
            " WHERE table_name = 'ingredients' AND action = 'd'"
        )
    )
    change = await adb.scalar(
        text("SELECT change_id FROM revisions WHERE table_name = 'ingredients' AND action = 'd'")
    )
    refused = await mo.post(f"/api/changes/{change}/revert")
    assert refused.status_code == 409 and "kept whole" in refused.json()["detail"]


async def test_a_removal_now_keeps_the_whole_row(adb) -> None:
    await _fresh_change(adb)
    await adb.execute(text("INSERT INTO ingredients (name, match_key) VALUES ('Sumac', 'sumac')"))
    await adb.execute(text("DELETE FROM ingredients WHERE name = 'Sumac'"))
    changes = await adb.scalar(
        text("SELECT changes FROM revisions WHERE table_name = 'ingredients' AND action = 'd'")
    )
    assert changes["match_key"] == ["sumac", None] and "created_at" in changes
