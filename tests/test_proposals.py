"""Proposed changes to published recipes (routers/proposals.py)."""

from sqlalchemy import text


async def _published(mo, adb, title="Shakshuka", page="12"):
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": []})).json()[
        "id"
    ]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    recipe = await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": title,
            "editions": [{"edition_id": edition, "page": page}],
            "ingredients": ["eggs"],
        },
    )
    assert recipe.status_code == 201, recipe.text
    return book, edition, recipe.json()["id"]


def _edit(edition, title="Shakshuka", page="14", lines=("eggs", "tomatoes")):
    return {
        "title": title,
        "editions": [{"edition_id": edition, "page": page}],
        "ingredients": list(lines),
    }


async def test_a_proposal_waits_and_changes_nothing(people, client, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    r = await con.post(
        f"/api/recipes/{recipe}/proposals", json={**_edit(edition), "reason": "It's on 14 in mine."}
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "open" and p["by"] == "con" and not p["changed_since"]
    differs = {d["label"]: d for d in p["differences"]}
    assert set(differs) == {"Where", "Ingredients"}
    assert (differs["Ingredients"]["now"], differs["Ingredients"]["proposed"]) == (
        "eggs",
        "eggs; tomatoes",
    )
    assert differs["Where"]["proposed"].endswith("page 14")
    assert p["kind"] == "recipe" and p["href"] == f"/recipes/{recipe}"
    shown = (await client.get(f"/api/recipes/{recipe}")).json()
    assert shown["ingredients"] == ["eggs"] and shown["pages"][0]["page"] == "12"
    # Nothing in the history from checking it.
    history = (await client.get(f"/api/recipes/{recipe}/history")).json()
    assert len(history) == 1


async def test_only_its_proposer_and_moderators_see_it(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    cy = await people("cy", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    await con.post(f"/api/recipes/{recipe}/proposals", json=_edit(edition))
    assert len((await con.get(f"/api/recipes/{recipe}/proposals")).json()) == 1
    assert (await cy.get(f"/api/recipes/{recipe}/proposals")).json() == []
    assert len((await mo.get(f"/api/recipes/{recipe}/proposals")).json()) == 1
    assert (await cy.get("/api/review/proposals")).status_code == 403
    assert len((await mo.get("/api/review/proposals")).json()) == 1


async def test_proposing_again_replaces_the_first(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    await con.post(f"/api/recipes/{recipe}/proposals", json=_edit(edition, page="14"))
    await con.post(f"/api/recipes/{recipe}/proposals", json=_edit(edition, page="15"))
    [p] = (await mo.get("/api/review/proposals")).json()
    [where] = [d for d in p["differences"] if d["label"] == "Where"]
    assert where["proposed"].endswith("page 15")


async def test_applying_saves_it_as_the_contributors(people, client, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    p = (await con.post(f"/api/recipes/{recipe}/proposals", json=_edit(edition))).json()
    assert (
        await con.post(f"/api/proposals/{p['id']}", json={"action": "apply"})
    ).status_code == 403
    r = await mo.post(f"/api/proposals/{p['id']}", json={"action": "apply"})
    assert r.status_code == 200 and r.json()["status"] == "applied"
    shown = (await client.get(f"/api/recipes/{recipe}")).json()
    assert shown["ingredients"] == ["eggs", "tomatoes"] and shown["pages"][0]["page"] == "14"
    newest = (await client.get(f"/api/recipes/{recipe}/history")).json()[0]
    assert newest["by"] == "con" and newest["via"] == f"proposal:{p['id']}"
    assert (await mo.post(f"/api/proposals/{p['id']}", json={"action": "apply"})).status_code == 404


async def test_a_change_since_needs_saying_so(people, client, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    p = (await con.post(f"/api/recipes/{recipe}/proposals", json=_edit(edition))).json()
    await mo.put(
        f"/api/recipes/{recipe}",
        json=_edit(edition, title="Green Shakshuka", page="12", lines=("eggs",)),
    )
    [waiting] = (await mo.get("/api/review/proposals")).json()
    assert waiting["changed_since"]
    refused = await mo.post(f"/api/proposals/{p['id']}", json={"action": "apply"})
    assert refused.status_code == 409 and "changed since" in refused.json()["detail"]
    r = await mo.post(f"/api/proposals/{p['id']}", json={"action": "apply", "anyway": True})
    assert r.status_code == 200
    assert (await client.get(f"/api/recipes/{recipe}")).json()["title"] == "Shakshuka"


async def test_declined_with_a_reason_or_withdrawn(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    p = (await con.post(f"/api/recipes/{recipe}/proposals", json=_edit(edition))).json()
    assert (
        await mo.post(f"/api/proposals/{p['id']}", json={"action": "decline"})
    ).status_code == 422
    r = await mo.post(
        f"/api/proposals/{p['id']}", json={"action": "decline", "note": "12 is right."}
    )
    assert (r.json()["status"], r.json()["note"]) == ("declined", "12 is right.")
    [mine] = (await con.get("/api/account/proposals")).json()
    assert mine["note"] == "12 is right."
    again = (await con.post(f"/api/recipes/{recipe}/proposals", json=_edit(edition))).json()
    cy = await people("cy", role="contributor")
    assert (await cy.delete(f"/api/proposals/{again['id']}")).status_code == 404
    assert (await con.delete(f"/api/proposals/{again['id']}")).status_code == 204
    assert (await mo.get("/api/review/proposals")).json() == []


async def test_what_cant_be_proposed(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    plain = await people("plain")
    book, edition, recipe = await _published(mo, adb)
    assert (
        await plain.post(f"/api/recipes/{recipe}/proposals", json=_edit(edition))
    ).status_code == 403
    assert (
        await mo.post(f"/api/recipes/{recipe}/proposals", json=_edit(edition))
    ).status_code == 409
    bad = await con.post(f"/api/recipes/{recipe}/proposals", json=_edit(edition, title="  "))
    assert bad.status_code == 422
    # Their own recipe waiting for review is changed directly.
    own = await con.post(
        f"/api/sources/{book}/recipes",
        json={"title": "Mine", "editions": [{"edition_id": edition}], "ingredients": []},
    )
    mine = own.json()["id"]
    assert (
        await con.post(f"/api/recipes/{mine}/proposals", json=_edit(edition))
    ).status_code == 409
    # A private collection's recipe isn't there to propose to.
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    fudge = (
        await ann.post(f"/api/sources/{box}/recipes", json={"title": "Fudge", "ingredients": []})
    ).json()["id"]
    assert (
        await con.post(f"/api/recipes/{fudge}/proposals", json=_edit(edition))
    ).status_code == 404


# A source's details


def _book_edit(adb_edition, title="Plenty More", year=2014, authors=("Yotam Ottolenghi",)):
    return {
        "title": title,
        "credits": [{"name": a} for a in authors],
        "editions": [{"id": adb_edition, "published_year": year}],
    }


async def test_a_book_change_is_proposed_and_applied(people, client, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    book, edition, _ = await _published(mo, adb)
    r = await con.post(
        f"/api/sources/{book}/proposals",
        json={**_book_edit(edition), "reason": "The cover says Plenty More."},
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["kind"] == "source" and p["recipe_id"] is None and p["href"] == f"/sources/{book}"
    differs = {d["label"]: d for d in p["differences"]}
    assert differs["Title"] == {"label": "Title", "now": "Plenty", "proposed": "Plenty More"}
    assert differs["Credits"]["proposed"] == "Yotam Ottolenghi (author)"
    assert "2014" in differs["Editions"]["proposed"]
    # Nothing changed yet.
    assert (await client.get(f"/api/sources/{book}")).json()["title"] == "Plenty"
    assert [x["id"] for x in (await mo.get("/api/review/proposals")).json()] == [p["id"]]
    applied = await mo.post(f"/api/proposals/{p['id']}", json={"action": "apply"})
    assert applied.status_code == 200, applied.text
    shown = (await client.get(f"/api/sources/{book}")).json()
    assert shown["title"] == "Plenty More"
    assert [c["credited_as"] for c in shown["credits"]] == ["Yotam Ottolenghi"]
    assert shown["editions"][0]["published_year"] == 2014
    newest = (await client.get(f"/api/sources/{book}/history")).json()[0]
    assert newest["by"] == "con" and newest["via"] == f"proposal:{p['id']}"


async def test_a_book_changed_since_needs_saying_so(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    book, edition, _ = await _published(mo, adb)
    p = (await con.post(f"/api/sources/{book}/proposals", json=_book_edit(edition))).json()
    # A recipe added to it isn't a change to its details.
    await mo.post(
        f"/api/sources/{book}/recipes",
        json={"title": "Another", "editions": [{"edition_id": edition}], "ingredients": []},
    )
    assert not (await mo.get("/api/review/proposals")).json()[0]["changed_since"]
    await mo.put(f"/api/sources/{book}", json={"title": "Plenty!", "credits": []})
    assert (await mo.get("/api/review/proposals")).json()[0]["changed_since"]
    refused = await mo.post(f"/api/proposals/{p['id']}", json={"action": "apply"})
    assert refused.status_code == 409


async def test_what_book_changes_cant_be_proposed(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    book, edition, _ = await _published(mo, adb)
    assert (
        await mo.post(f"/api/sources/{book}/proposals", json=_book_edit(edition))
    ).status_code == 409
    bad = await con.post(f"/api/sources/{book}/proposals", json=_book_edit(edition, title=" "))
    assert bad.status_code == 422
    own = (await con.post("/api/sources/manual", json={"title": "Mine", "authors": []})).json()[
        "id"
    ]
    assert (await con.post(f"/api/sources/{own}/proposals", json={"title": "X"})).status_code == 409
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    assert (await con.post(f"/api/sources/{box}/proposals", json={"title": "X"})).status_code == 404


async def test_a_moderator_sees_the_ingredients_a_change_would_add(people, adb) -> None:
    """The new-ingredient step for suggested changes: before applying, what
    it adds, with the names like each in case it's one written differently."""
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    book, edition, recipe = await _published(mo, adb)
    herbs = await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Herbs",
            "editions": [{"edition_id": edition, "page": "20"}],
            "ingredients": ["Fresh Chives"],
        },
    )
    assert herbs.status_code == 201, herbs.text
    await con.post(
        f"/api/recipes/{recipe}/proposals",
        json=_edit(edition, lines=("eggs", "Chives", "Zaatar (p. 9)", "Eggs or Sumac")),
    )
    [p] = (await mo.get("/api/review/proposals")).json()
    new = {n["name"]: [s["name"] for s in n["similar"]] for n in p["new_ingredients"]}
    # eggs is here; a page reference is a component, not an ingredient.
    assert set(new) == {"Chives", "Sumac"}
    assert "Fresh Chives" in new["Chives"]
    # Once applied, nothing's new any more.
    r = await mo.post(f"/api/proposals/{p['id']}", json={"action": "apply"})
    assert r.status_code == 200, r.text
    assert r.json()["new_ingredients"] == []


# A recipe's equipment, proposed as its ingredients are


def _needs(shown: dict) -> tuple[bool, list[str]]:
    return shown["equipment_checked"], [n["text"] for n in shown["equipment"]]


async def test_equipment_is_proposed_as_ingredients_are(people, client, adb) -> None:
    """ "Add it", for someone who can't change the recipe (Ray's equipment
    spec, 2026-11-15): it waits, is shown beside what's recorded, and is
    saved as theirs when a moderator applies it."""
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    same = _edit(edition, page="12", lines=("eggs",))
    proposed = await con.post(
        f"/api/recipes/{recipe}/proposals",
        json={**same, "equipment": ["stand mixer or hand mixer", "9 inch springform tin", "wok"]},
    )
    assert proposed.status_code == 201, proposed.text
    p = proposed.json()
    # Only the equipment differs, worded as saving will word it: the list's
    # names, by another name too, and the size before its thing.
    assert [(d["label"], d["now"], d["proposed"]) for d in p["differences"]] == [
        (
            "Equipment",
            "Not recorded",
            "Stand mixer or Hand mixer; 9 inch Springform pan; Wok",
        )
    ]
    assert p["new_equipment"] == []
    # It waits: nothing of it is on the recipe, or in its history.
    assert _needs((await client.get(f"/api/recipes/{recipe}")).json()) == (False, [])
    assert len((await client.get(f"/api/recipes/{recipe}/history")).json()) == 1
    assert await adb.scalar(text("SELECT count(*) FROM recipe_equipment")) == 0

    applied = await mo.post(f"/api/proposals/{p['id']}", json={"action": "apply"})
    assert applied.status_code == 200, applied.text
    assert applied.json()["differences"] == []
    assert _needs((await client.get(f"/api/recipes/{recipe}")).json()) == (
        True,
        ["Stand mixer or Hand mixer", "9 inch Springform pan", "Wok"],
    )
    # The contributor's change, in the history.
    by = await adb.scalars(
        text(
            "SELECT DISTINCT u.display_name FROM revisions r JOIN users u ON u.id = r.user_id"
            " WHERE r.table_name = 'recipe_equipment'"
        )
    )
    assert by.all() == ["con"]


async def test_a_proposals_equipment_is_shown_in_its_three_states(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    same = _edit(edition, page="12", lines=("eggs",))

    async def differs(**equipment) -> list[tuple[str, str, str]]:
        r = await con.post(f"/api/recipes/{recipe}/proposals", json={**same, **equipment})
        assert r.status_code == 201, r.text
        return [(d["label"], d["now"], d["proposed"]) for d in r.json()["differences"]]

    # A change that says nothing of equipment leaves it as it is.
    assert await differs() == []
    assert await differs(equipment=[], nothing_special=True) == [
        ("Equipment", "Not recorded", "Nothing special")
    ]
    # Recorded now: taking it all away is "not recorded", not "nothing special".
    edit = await mo.put(f"/api/recipes/{recipe}", json={**same, "equipment": ["wok"]})
    assert edit.status_code == 200, edit.text
    assert await differs(equipment=["Wok"]) == []
    assert await differs(equipment=[], nothing_special=False) == [
        ("Equipment", "Wok", "Not recorded")
    ]
    assert await differs(equipment=["wok", "blender"]) == [("Equipment", "Wok", "Wok; Blender")]
    # A change that says nothing still says nothing, with equipment recorded;
    # and applying it leaves the equipment there.
    assert await differs() == []
    [p] = (await mo.get("/api/review/proposals")).json()
    assert (
        await mo.post(f"/api/proposals/{p['id']}", json={"action": "apply", "anyway": True})
    ).status_code == 200
    assert _needs((await mo.get(f"/api/recipes/{recipe}")).json()) == (True, ["Wok"])


async def test_equipment_saving_would_refuse_cant_be_proposed(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    same = _edit(edition, page="12", lines=("eggs",))
    for equipment, why in (
        ({"equipment": ["mixing bowl"]}, "expected in any kitchen"),
        ({"equipment": ["9-inch"]}, "is a size"),
        ({"equipment": ["wok"], "nothing_special": True}, "Nothing special"),
    ):
        refused = await con.post(f"/api/recipes/{recipe}/proposals", json={**same, **equipment})
        assert refused.status_code == 422, refused.text
        assert why in refused.json()["detail"]
    assert (await mo.get("/api/review/proposals")).json() == []
    assert await adb.scalar(text("SELECT count(*) FROM equipment WHERE NOT listed")) == 0


async def test_a_moderator_sees_the_equipment_a_change_would_add(people, client, adb) -> None:
    """As for ingredients: before applying, what it adds to the catalog,
    with what's named like each in case it's one written differently."""
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    same = _edit(edition, page="12", lines=("eggs",))
    proposed = await con.post(
        f"/api/recipes/{recipe}/proposals",
        json={**same, "equipment": ["wafle iron or wok", "egg coddler"]},
    )
    assert proposed.status_code == 201, proposed.text
    [p] = (await mo.get("/api/review/proposals")).json()
    new = {n["name"]: [s["name"] for s in n["similar"]] for n in p["new_equipment"]}
    # Wok is in the list.
    assert set(new) == {"Wafle iron", "Egg coddler"}
    assert new["Wafle iron"][0] == "Waffle iron"
    assert [d["proposed"] for d in p["differences"]] == ["Wafle iron or Wok; Egg coddler"]
    # Proposing made nothing: the things come with the change, if it's applied.
    assert await adb.scalar(text("SELECT count(*) FROM equipment WHERE NOT listed")) == 0
    assert (await mo.post(f"/api/proposals/{p['id']}", json={"action": "apply"})).status_code == 200
    assert await adb.scalar(text("SELECT count(*) FROM equipment WHERE NOT listed")) == 2
    # Applied, it adds nothing more, and nothing is listed as new.
    [mine] = (await con.get("/api/account/proposals")).json()
    assert (mine["status"], mine["new_equipment"]) == ("applied", [])


async def test_a_proposal_doesnt_name_a_hidden_thing(people, adb) -> None:
    """A thing only a private recipe needs isn't the proposer's, or a
    moderator's, to learn of: it's worded as typed, and counted new."""
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    stew = await ann.post(
        f"/api/sources/{box}/recipes",
        json={"title": "Stew", "ingredients": ["Egg"], "equipment": ["Nana's CAULDRON"]},
    )
    assert stew.status_code == 201, stew.text
    _, edition, recipe = await _published(mo, adb)
    same = _edit(edition, page="12", lines=("eggs",))
    proposed = await con.post(
        f"/api/recipes/{recipe}/proposals", json={**same, "equipment": ["nana's cauldron"]}
    )
    assert proposed.status_code == 201, proposed.text
    for seen_by in (proposed.json(), (await mo.get("/api/review/proposals")).json()[0]):
        assert [d["proposed"] for d in seen_by["differences"]] == ["Nana's cauldron"]
        assert seen_by["new_equipment"] == [{"name": "Nana's cauldron", "similar": []}]


async def test_equipment_changed_since_needs_saying_so(people, adb) -> None:
    """A recipe's equipment changing is the recipe changing: a proposal
    made before it would write over it."""
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    _, edition, recipe = await _published(mo, adb)
    same = _edit(edition, page="12", lines=("eggs",))
    await con.post(f"/api/recipes/{recipe}/proposals", json={**same, "equipment": ["wok"]})
    [before] = (await mo.get("/api/review/proposals")).json()
    assert not before["changed_since"]
    edit = await mo.put(f"/api/recipes/{recipe}", json={**same, "equipment": ["blender"]})
    assert edit.status_code == 200, edit.text
    [after] = (await mo.get("/api/review/proposals")).json()
    assert after["changed_since"]
    assert [(d["now"], d["proposed"]) for d in after["differences"]] == [("Blender", "Wok")]
    assert (
        await mo.post(f"/api/proposals/{after['id']}", json={"action": "apply"})
    ).status_code == 409
