"""Changing the equipment list (equipment.py, routers/equipment.py): the
moderators' tools, each change in the edit history and undone from it, and
a merged thing's address. *Ray's spec, 2026-11-15.*

Nothing on the site records a recipe's needs yet, so the tests that need
one write the rows as the recipe form will."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in, make_admins


@pytest.fixture
async def mo(people):
    return await people("mo", role="moderator")


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


async def _id(adb, name: str) -> str:
    found = await adb.scalar(text("SELECT id FROM equipment WHERE name = :n"), {"n": name})
    assert found is not None, name
    return str(found)


async def _shown(c, thing: str) -> dict:
    response = await c.get(f"/api/equipment/{thing}")
    assert response.status_code == 200, response.text
    return response.json()


async def _add(c, name: str, **more) -> str:
    made = await c.post("/api/equipment", json={"name": name, **more})
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def _recipe(c, title: str) -> str:
    book = (
        await c.post("/api/sources/manual", json={"title": f"{title} Book", "authors": ["Ann"]})
    ).json()["id"]
    editions = (await c.get(f"/api/sources/{book}")).json()["editions"]
    made = await c.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": title,
            "ingredients": ["Egg"],
            "editions": [{"edition_id": editions[0]["id"], "page": "1"}],
        },
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def _need(adb, recipe: str, position: int, *things: str) -> None:
    need = await adb.scalar(
        text("INSERT INTO recipe_equipment (recipe_id, position) VALUES (:r, :p) RETURNING id"),
        {"r": uuid.UUID(recipe), "p": position},
    )
    for rank, thing in enumerate(things, start=1):
        await adb.execute(
            text(
                "INSERT INTO equipment_options (recipe_equipment_id, recipe_id, rank, equipment_id)"
                " VALUES (:n, :r, :k, :e)"
            ),
            {"n": need, "r": uuid.UUID(recipe), "k": rank, "e": uuid.UUID(thing)},
        )


async def _needs(adb, recipe: str) -> list[list[str]]:
    """A recipe's needs in order, each as the names that meet it, by rank."""
    rows = await adb.execute(
        text(
            "SELECT n.position, e.name FROM recipe_equipment n"
            " JOIN equipment_options o ON o.recipe_equipment_id = n.id"
            " JOIN equipment e ON e.id = o.equipment_id"
            " WHERE n.recipe_id = :r ORDER BY n.position, o.rank"
        ),
        {"r": uuid.UUID(recipe)},
    )
    out: dict[int, list[str]] = {}
    for position, name in rows:
        out.setdefault(position, []).append(name)
    return list(out.values())


# Who may


async def test_only_a_moderator_changes_the_list(people, client, adb) -> None:
    wok, grill = await _id(adb, "Wok"), await _id(adb, "Grill")
    plain = await people("plain")
    con = await people("con", role="contributor")
    changes = [
        ("post", "/api/equipment", {"name": "Egg coddler"}),
        ("patch", f"/api/equipment/{wok}", {"name": "Wok pan"}),
        ("put", f"/api/equipment/{wok}/assumed", {"assumed": True}),
        ("post", f"/api/equipment/{wok}/merge", {"into": grill}),
        ("delete", f"/api/equipment/{wok}", None),
        ("post", f"/api/equipment/{wok}/aliases", {"name": "Kadai"}),
        ("put", f"/api/equipment/{wok}/counts-as/{grill}", None),
        ("delete", f"/api/equipment/{wok}/counts-as/{grill}", None),
    ]
    for who, refused in ((client, 401), (plain, 403), (con, 403)):
        for method, path, body in changes:
            kwargs = {"json": body} if body is not None else {}
            response = await getattr(who, method)(path, **kwargs)
            assert response.status_code == refused, (method, path, response.text)
    assert (await _shown(client, wok))["name"] == "Wok"
    assert await adb.scalar(text("SELECT count(*) FROM equipment WHERE name = 'Egg coddler'")) == 0


# Adding and renaming


async def test_a_moderator_adds_a_thing(mo, client) -> None:
    coddler = await _add(mo, "  Egg   coddler ")
    shown = await _shown(client, coddler)
    assert (shown["name"], shown["assumed"]) == ("Egg coddler", False)
    listed = (await client.get("/api/equipment", params={"q": "coddler"})).json()["equipment"]
    assert [e["name"] for e in listed] == ["Egg coddler"]
    # And one any kitchen has, which is listed only when asked for.
    kettle = await _add(mo, "Kettle", assumed=True)
    assert (await _shown(client, kettle))["assumed"] is True
    assert (await client.get("/api/equipment", params={"q": "kettle"})).json()["total"] == 0


async def test_a_name_means_one_thing(mo, adb) -> None:
    mixer = await _id(adb, "Stand mixer")
    blender = await _id(adb, "Immersion blender")
    # A thing's name, however it's written, and another name for one.
    for name, holder in (("stand mixers", mixer), ("Stick Blender", blender)):
        taken = await mo.post("/api/equipment", json={"name": name})
        assert taken.status_code == 409, taken.text
        assert taken.json()["detail"]["equipment"]["id"] == holder
        renamed = await mo.patch(f"/api/equipment/{await _id(adb, 'Wok')}", json={"name": name})
        assert renamed.status_code == 409
        assert renamed.json()["detail"]["equipment"]["id"] == holder
        also = await mo.post(f"/api/equipment/{await _id(adb, 'Wok')}/aliases", json={"name": name})
        assert also.status_code == 409
    nothing = await mo.post("/api/equipment", json={"name": "!!!"})
    assert nothing.status_code == 422
    assert nothing.json()["detail"] == "A name needs at least one letter or number."


async def test_a_renamed_thing_is_still_found_by_its_old_name(mo, client, adb) -> None:
    wok = await _id(adb, "Wok")
    renamed = await mo.patch(f"/api/equipment/{wok}", json={"name": "Carbon steel wok"})
    assert renamed.json() == {"id": wok, "name": "Carbon steel wok"}
    shown = await _shown(client, wok)
    assert shown["name"] == "Carbon steel wok"
    assert [a["name"] for a in shown["aliases"]] == ["Wok"]
    # Only how it's written: no other name is kept for that.
    await mo.patch(f"/api/equipment/{wok}", json={"name": "Carbon Steel Woks"})
    assert [a["name"] for a in (await _shown(client, wok))["aliases"]] == ["Wok"]
    # Back to a name it had: that name is its name, not another name too.
    await mo.patch(f"/api/equipment/{wok}", json={"name": "Wok"})
    shown = await _shown(client, wok)
    assert shown["name"] == "Wok"
    assert [a["name"] for a in shown["aliases"]] == ["Carbon Steel Woks"]


# Other names


async def test_another_name_is_added_and_taken_away(mo, client, adb) -> None:
    wok = await _id(adb, "Wok")
    added = await mo.post(f"/api/equipment/{wok}/aliases", json={"name": "Kadai"})
    assert added.status_code == 201, added.text
    assert added.json()["name"] == "Kadai"
    found = (await client.get("/api/equipment", params={"q": "kadai"})).json()["equipment"]
    assert [e["name"] for e in found] == ["Wok"]
    # Its own name, or one it has, isn't added again.
    for name in ("woks", "KADAI"):
        again = await mo.post(f"/api/equipment/{wok}/aliases", json={"name": name})
        assert again.status_code == 422, name
        assert "already finds “Wok”" in again.json()["detail"]
    # Another thing's other name isn't this one's to take away.
    other = await mo.delete(
        f"/api/equipment/{await _id(adb, 'Grill')}/aliases/{added.json()['id']}"
    )
    assert other.status_code == 404
    gone = await mo.delete(f"/api/equipment/{wok}/aliases/{added.json()['id']}")
    assert gone.status_code == 204
    assert (await _shown(client, wok))["aliases"] == []


# What counts as what


async def test_a_thing_is_made_to_count_as_another_and_stopped(mo, client, adb) -> None:
    wok, pan = await _id(adb, "Wok"), await _id(adb, "Paella pan")
    dutch = await _id(adb, "Dutch oven")
    for broader in (pan, dutch, pan):
        made = await mo.put(f"/api/equipment/{wok}/counts-as/{broader}")
        assert made.status_code == 200, made.text
    # Several, each once.
    assert [c["name"] for c in (await _shown(client, wok))["counts_as"]] == [
        "Dutch oven",
        "Paella pan",
    ]
    assert [c["name"] for c in (await _shown(client, pan))["includes"]] == ["Wok"]
    stopped = await mo.delete(f"/api/equipment/{wok}/counts-as/{pan}")
    assert stopped.status_code == 204
    assert [c["name"] for c in (await _shown(client, wok))["counts_as"]] == ["Dutch oven"]


async def test_nothing_counts_as_itself_or_round_in_a_ring(mo, adb) -> None:
    mixer, stand = await _id(adb, "Mixer"), await _id(adb, "Stand mixer")
    itself = await mo.put(f"/api/equipment/{mixer}/counts-as/{mixer}")
    assert (itself.status_code, itself.json()["detail"]) == (
        422,
        "A thing can't count as itself.",
    )
    # A stand mixer counts as a mixer, so a mixer can't count as one.
    ring = await mo.put(f"/api/equipment/{mixer}/counts-as/{stand}")
    assert ring.status_code == 422
    assert ring.json()["detail"].startswith("“Stand mixer” already counts as “Mixer”")
    # Nor by way of a third.
    planetary = await _add(mo, "Planetary mixer")
    assert (await mo.put(f"/api/equipment/{planetary}/counts-as/{stand}")).status_code == 200
    assert (await mo.put(f"/api/equipment/{mixer}/counts-as/{planetary}")).status_code == 422
    missing = await mo.put(f"/api/equipment/{mixer}/counts-as/{uuid.uuid4()}")
    assert missing.status_code == 404


# What any kitchen has


async def test_a_thing_becomes_any_kitchens_unless_a_recipe_lists_it(mo, client, adb) -> None:
    wok, tagine = await _id(adb, "Wok"), await _id(adb, "Tagine")
    await _need(adb, await _recipe(mo, "Lamb Tagine"), 1, tagine)
    marked = await mo.put(f"/api/equipment/{wok}/assumed", json={"assumed": True})
    assert marked.status_code == 200, marked.text
    assert (await _shown(client, wok))["assumed"] is True
    assert (await client.get("/api/equipment", params={"q": "wok"})).json()["total"] == 0
    refused = await mo.put(f"/api/equipment/{tagine}/assumed", json={"assumed": True})
    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("1 recipe lists “Tagine”.")
    assert (await _shown(client, tagine))["assumed"] is False
    # And back: a recipe can list it again.
    await mo.put(f"/api/equipment/{wok}/assumed", json={"assumed": False})
    assert (await _shown(client, wok))["assumed"] is False


# Merging


async def test_merging_moves_everything_to_the_one_kept(mo, client, adb) -> None:
    stand, hand = await _id(adb, "Stand mixer"), await _id(adb, "Hand mixer")
    mixer, processor = await _id(adb, "Mixer"), await _id(adb, "Food processor")
    planetary = await _add(mo, "Planetary mixer")
    await mo.put(f"/api/equipment/{planetary}/counts-as/{hand}")
    await mo.post(f"/api/equipment/{hand}/aliases", json={"name": "Electric beaters"})
    cake, torte = await _recipe(mo, "Sponge"), await _recipe(mo, "Torte")
    # One need offers both; one names the one going first; one only it.
    await _need(adb, cake, 1, stand, hand)
    await _need(adb, cake, 2, hand, processor)
    await _need(adb, torte, 1, hand)

    merged = await mo.post(f"/api/equipment/{hand}/merge", json={"into": stand})
    assert merged.json() == {"id": stand, "name": "Stand mixer"}
    assert (await client.get(f"/api/equipment/{hand}")).status_code == 404
    assert await _needs(adb, cake) == [["Stand mixer"], ["Stand mixer", "Food processor"]]
    assert await _needs(adb, torte) == [["Stand mixer"]]
    shown = await _shown(client, stand)
    assert shown["total"] == 2
    # Its name and its other names are the kept one's other names.
    assert {a["name"] for a in shown["aliases"]} == {"Hand mixer", "Electric beaters"}
    # Both counted as a mixer: once. What counted as the one going does now
    # of the one kept.
    assert [c["name"] for c in shown["counts_as"]] == ["Mixer"]
    assert [c["name"] for c in shown["includes"]] == ["Planetary mixer"]
    assert [c["name"] for c in (await _shown(client, mixer))["includes"]] == ["Stand mixer"]
    found = (await client.get("/api/equipment", params={"q": "hand mixer"})).json()["equipment"]
    assert [e["name"] for e in found] == ["Stand mixer"]


async def test_merging_a_thing_into_what_it_counts_as_leaves_no_ring(mo, client, adb) -> None:
    stand, mixer = await _id(adb, "Stand mixer"), await _id(adb, "Mixer")
    merged = await mo.post(f"/api/equipment/{stand}/merge", json={"into": mixer})
    assert merged.status_code == 200, merged.text
    shown = await _shown(client, mixer)
    assert shown["counts_as"] == []
    assert [c["name"] for c in shown["includes"]] == ["Hand mixer"]
    # And the other way: the broader into the narrower.
    grill, gas = await _id(adb, "Grill"), await _id(adb, "Gas grill")
    await mo.post(f"/api/equipment/{grill}/merge", json={"into": gas})
    shown = await _shown(client, gas)
    assert shown["counts_as"] == []
    assert [c["name"] for c in shown["includes"]] == ["Charcoal grill"]
    links = await adb.scalar(
        text("SELECT count(*) FROM equipment_counts_as WHERE equipment_id = counts_as_id")
    )
    assert links == 0


async def test_a_merge_that_would_make_a_ring_drops_the_link(mo, client, adb) -> None:
    """A into B, where B counted as C and C as A: B can't count as C and C
    as B."""
    a, b, c = [await _add(mo, name) for name in ("Ring A", "Ring B", "Ring C")]
    assert (await mo.put(f"/api/equipment/{b}/counts-as/{c}")).status_code == 200
    assert (await mo.put(f"/api/equipment/{c}/counts-as/{a}")).status_code == 200
    assert (await mo.post(f"/api/equipment/{a}/merge", json={"into": b})).status_code == 200
    shown = await _shown(client, b)
    assert shown["counts_as"] == []
    assert [x["name"] for x in shown["includes"]] == ["Ring C"]


async def test_what_cant_be_merged(mo, adb) -> None:
    wok, tagine = await _id(adb, "Wok"), await _id(adb, "Tagine")
    skillet = await _id(adb, "Skillet")
    itself = await mo.post(f"/api/equipment/{wok}/merge", json={"into": wok})
    assert (itself.status_code, itself.json()["detail"]) == (
        422,
        "A thing can't be merged into itself.",
    )
    missing = await mo.post(f"/api/equipment/{wok}/merge", json={"into": str(uuid.uuid4())})
    assert missing.status_code == 404
    # What a recipe lists can't become what no recipe may list.
    await _need(adb, await _recipe(mo, "Lamb Tagine"), 1, tagine)
    assumed = await mo.post(f"/api/equipment/{tagine}/merge", json={"into": skillet})
    assert assumed.status_code == 409
    assert "expected in any kitchen" in assumed.json()["detail"]
    # One no recipe lists can.
    assert (await mo.post(f"/api/equipment/{wok}/merge", json={"into": skillet})).status_code == 200


async def test_a_merged_things_address_goes_to_the_one_kept(mo, client, adb) -> None:
    wok, pan = await _id(adb, "Wok"), await _id(adb, "Paella pan")
    griddle = await _id(adb, "Griddle")
    await mo.post(f"/api/equipment/{wok}/merge", json={"into": pan})
    moved = await client.get(f"/equipment/{wok}", follow_redirects=False)
    assert (moved.status_code, moved.headers["location"]) == (301, f"/equipment/{pan}")
    # Merged on, the first address follows.
    await mo.post(f"/api/equipment/{pan}/merge", json={"into": griddle})
    moved = await client.get(f"/equipment/{wok}", follow_redirects=False)
    assert (moved.status_code, moved.headers["location"]) == (301, f"/equipment/{griddle}")
    assert (
        await client.get(f"/equipment/{uuid.uuid4()}", follow_redirects=False)
    ).status_code == 404


# Deleting


async def test_only_a_thing_nothing_uses_is_deleted(mo, client, adb) -> None:
    wok, tagine, mixer = await _id(adb, "Wok"), await _id(adb, "Tagine"), await _id(adb, "Mixer")
    stand = await _id(adb, "Stand mixer")
    await _need(adb, await _recipe(mo, "Lamb Tagine"), 1, tagine)
    listed = await mo.delete(f"/api/equipment/{tagine}")
    assert listed.status_code == 409
    assert listed.json()["detail"] == "1 recipe lists “Tagine”. Merge it into another instead."
    counted = await mo.delete(f"/api/equipment/{mixer}")
    assert counted.status_code == 409
    assert counted.json()["detail"].startswith("Something counts as “Mixer”.")
    # One that only counts as something goes, with that and its names.
    assert (await mo.delete(f"/api/equipment/{stand}")).status_code == 204
    assert (await mo.delete(f"/api/equipment/{wok}")).status_code == 204
    assert (await client.get(f"/api/equipment/{wok}")).status_code == 404
    assert (await mo.delete(f"/api/equipment/{wok}")).status_code == 404


# The edit history


async def _history(c, thing: str) -> list[dict]:
    response = await c.get(f"/api/equipment/{thing}/history")
    assert response.status_code == 200, response.text
    return response.json()


def _said(change: dict) -> list[tuple]:
    """A change as (what, action, name, {field: [before, after]})."""
    return [
        (
            e["what"],
            e["action"],
            e["name"],
            {f["field"]: [f["before"], f["after"]] for f in e["fields"]},
        )
        for e in change["entries"]
    ]


async def test_the_list_as_it_started_has_no_history(client, adb) -> None:
    """Seeds aren't edits: the triggers start after them (migration 0080)."""
    assert await adb.scalar(text("SELECT count(*) FROM revisions")) == 0
    assert await _history(client, await _id(adb, "Multicooker")) == []
    assert (await client.get(f"/api/equipment/{uuid.uuid4()}/history")).status_code == 404


async def test_every_change_to_a_thing_is_in_its_history(mo, client, adb) -> None:
    wok, pan = await _id(adb, "Wok"), await _id(adb, "Paella pan")
    await mo.patch(f"/api/equipment/{wok}", json={"name": "Carbon steel wok"})
    await mo.post(f"/api/equipment/{wok}/aliases", json={"name": "Kadai"})
    await mo.put(f"/api/equipment/{wok}/counts-as/{pan}")
    await mo.put(f"/api/equipment/{wok}/assumed", json={"assumed": True})
    newest_first = await _history(client, wok)
    assert [c["by"] for c in newest_first] == ["mo"] * 4
    assumed, counts, also, renamed = [_said(c) for c in newest_first]
    assert assumed == [("equipment", "changed", "Carbon steel wok", {"assumed": [False, True]})]
    assert counts == [
        (
            "thing it counts as",
            "added",
            "Paella pan",
            {"counts_as_id": [None, "Paella pan"], "equipment_id": [None, "Carbon steel wok"]},
        )
    ]
    [(what, action, name, fields)] = also
    assert (what, action, name) == ("equipment name", "added", "Kadai")
    assert fields["equipment_id"] == [None, "Carbon steel wok"]
    # A rename is the new name, and the old one kept as another name.
    assert (
        "equipment",
        "changed",
        "Carbon steel wok",
        {"name": ["Wok", "Carbon steel wok"]},
    ) in renamed
    assert [e for e in renamed if e[:3] == ("equipment name", "added", "Wok")]
    # The thing it was made to count as has none of this.
    assert await _history(client, pan) == []


async def test_moderators_see_the_lists_changes_among_the_latest(mo, people, adb) -> None:
    await mo.patch(f"/api/equipment/{await _id(adb, 'Wok')}", json={"name": "Carbon steel wok"})
    latest = (await mo.get("/api/changes")).json()
    assert ("equipment", "changed", "Carbon steel wok") in [e[:3] for e in _said(latest[0])]
    assert (await (await people("plain")).get("/api/changes")).status_code == 403


async def test_a_change_is_undone_from_the_history(mo, client, adb) -> None:
    wok, pan = await _id(adb, "Wok"), await _id(adb, "Paella pan")
    await mo.patch(f"/api/equipment/{wok}", json={"name": "Carbon steel wok"})
    await mo.put(f"/api/equipment/{wok}/counts-as/{pan}")
    await mo.put(f"/api/equipment/{wok}/assumed", json={"assumed": True})
    assumed, counts, renamed = await _history(client, wok)

    # The newest first: a later change to the same row stands in the way,
    # as it does for any record (revert.py).
    blocked = await mo.post(f"/api/changes/{renamed['id']}/revert")
    assert blocked.status_code == 409, blocked.text
    assert "later change" in blocked.json()["detail"]
    for change in (assumed, counts):
        undone = await mo.post(f"/api/changes/{change['id']}/revert")
        assert undone.status_code == 200, undone.text
    shown = await _shown(client, wok)
    assert (shown["name"], shown["assumed"]) == ("Carbon steel wok", False)
    assert shown["counts_as"] == []
    # Each undo is a change of its own.
    assert len(await _history(client, wok)) == 5
    # Undoing isn't for everyone.
    plain = await client.post(f"/api/changes/{assumed['id']}/revert")
    assert plain.status_code == 401


async def test_undoing_a_rename_puts_the_key_back_with_the_name(mo, client, adb) -> None:
    """The key is made from the name, and the history leaves it out of a
    change as noise. Undone without it, the thing had its old name and was
    found by its new one."""
    wok = await _id(adb, "Wok")
    await mo.patch(f"/api/equipment/{wok}", json={"name": "Carbon steel wok"})
    [renamed] = await _history(client, wok)
    undone = await mo.post(f"/api/changes/{renamed['id']}/revert")
    assert undone.status_code == 200, undone.text
    shown = await _shown(client, wok)
    assert shown["name"] == "Wok" and shown["aliases"] == []
    key = await adb.scalar(text("SELECT match_key FROM equipment WHERE id = :i"), {"i": wok})
    assert key == "wok"
    # So the name it was given for a moment is free again, and its own isn't.
    assert (await mo.post("/api/equipment", json={"name": "Woks"})).status_code == 409
    assert (await mo.post("/api/equipment", json={"name": "Carbon steel wok"})).status_code == 201


async def test_a_deleted_thing_is_put_back(mo, client, adb) -> None:
    stand = await _id(adb, "Stand mixer")
    await mo.post(f"/api/equipment/{stand}/aliases", json={"name": "Planetary mixer"})
    assert (await mo.delete(f"/api/equipment/{stand}")).status_code == 204
    deleted = (await mo.get("/api/changes")).json()[0]
    assert ("equipment", "removed", "Stand mixer") in [e[:3] for e in _said(deleted)]
    undone = await mo.post(f"/api/changes/{deleted['id']}/revert")
    assert undone.status_code == 200, undone.text
    shown = await _shown(client, stand)
    assert shown["name"] == "Stand mixer"
    assert [a["name"] for a in shown["aliases"]] == ["Planetary mixer"]
    assert [c["name"] for c in shown["counts_as"]] == ["Mixer"]
    # Whole, its key too: its name, however written, is taken again.
    assert (await mo.post("/api/equipment", json={"name": "stand mixers"})).status_code == 409


async def test_a_recipes_needs_are_recorded_with_the_recipe(mo, adb) -> None:
    """Nothing writes one yet; the day something does, it is the recipe's
    history, as an ingredient line is."""
    cake = await _recipe(mo, "Sponge")
    await _need(adb, cake, 1, await _id(adb, "Stand mixer"))
    rows = await adb.execute(
        text(
            "SELECT table_name, recipe_id, source_id IS NOT NULL, parent_id FROM revisions"
            " WHERE table_name IN ('recipe_equipment', 'equipment_options') ORDER BY id"
        )
    )
    stand = uuid.UUID(await _id(adb, "Stand mixer"))
    assert [tuple(r) for r in rows] == [
        ("recipe_equipment", uuid.UUID(cake), True, None),
        ("equipment_options", uuid.UUID(cake), True, stand),
    ]
    history = (await mo.get(f"/api/recipes/{cake}/history")).json()
    assert ("equipment choice", "added") in [e[:2] for c in history for e in _said(c)]
