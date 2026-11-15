"""Diets from Admin: adding one with what it avoids, renaming and removing
(routers/substitutions.py). *Ray, 2026-11-14.*"""

from sqlalchemy import text


async def _diets(client) -> dict[str, dict]:
    return {d["name"]: d for d in (await client.get("/api/diets")).json()}


async def _tag(client, kind: str, name: str) -> str:
    return next(
        t["id"]
        for t in (await client.get("/api/tags")).json()
        if t["kind"] == kind and t["name"] == name
    )


async def _book(mo, adb, title: str = "Plenty") -> tuple[str, str]:
    book = (await mo.post("/api/sources/manual", json={"title": title})).json()["id"]
    edition = await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    return book, str(edition)


async def _recipe(mo, book: str, edition: str, title: str, lines: tuple[str, ...] = ()) -> str:
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": title,
            "editions": [{"edition_id": edition, "page": "1"}],
            "ingredients": list(lines),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _tags_of(client, recipe: str) -> list[str]:
    return [t["name"] for t in (await client.get(f"/api/recipes/{recipe}")).json()["tags"]]


async def test_a_diet_is_added_with_what_it_avoids(people, client) -> None:
    mo = await people("mo", role="moderator")
    made = await mo.post(
        "/api/diets", json={"name": "  Low  FODMAP ", "allergens": ["wheat", "milk"]}
    )
    assert made.status_code == 200, made.text
    # In the allergens' own order, as the list gives them.
    assert (made.json()["name"], made.json()["avoids"]) == ("Low FODMAP", ["milk", "wheat"])
    assert (await _diets(client))["Low FODMAP"]["avoids"] == ["milk", "wheat"]
    # A tag like the others, for recipes and sources.
    assert await _tag(client, "diet", "Low FODMAP") == made.json()["id"]

    # Avoiding nothing is a diet too.
    plain = await mo.post("/api/diets", json={"name": "Whole30", "allergens": []})
    assert plain.status_code == 200 and plain.json()["avoids"] == []


async def test_a_name_thats_taken_is_refused_from_admin_and_found_for_a_swap(
    people, client
) -> None:
    mo = await people("mo", role="moderator")
    before = (await _diets(client))["Dairy-Free"]
    taken = await mo.post("/api/diets", json={"name": "dairy-free", "allergens": ["egg"]})
    assert taken.status_code == 409
    assert "Dairy-Free" in taken.json()["detail"]
    # And what it avoids wasn't written over.
    assert (await _diets(client))["Dairy-Free"] == before
    # A swap's form gives only the name, and gets the diet there is.
    found = await mo.post("/api/diets", json={"name": "dairy-free"})
    assert found.status_code == 200
    assert (found.json()["id"], found.json()["avoids"]) == (before["id"], ["milk"])


async def test_a_new_diet_needs_a_name_and_known_allergens(people, client) -> None:
    mo = await people("mo", role="moderator")
    unknown = await mo.post("/api/diets", json={"name": "Nightshade-Free", "allergens": ["nuts"]})
    assert unknown.status_code == 422 and "nuts" in unknown.json()["detail"]
    assert "Nightshade-Free" not in await _diets(client)
    blank = await mo.post("/api/diets", json={"name": "   ", "allergens": []})
    assert blank.status_code == 422
    long = await mo.post("/api/diets", json={"name": "x" * 61, "allergens": []})
    assert long.status_code == 422


async def test_a_diet_is_renamed_where_its_used(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book, edition = await _book(mo, adb)
    cake = await _recipe(mo, book, edition, "Rhubarb Cake")
    paleo = (await _diets(client))["Paleo"]["id"]
    assert (await mo.put(f"/api/recipes/{cake}/tags", json={"tags": [paleo]})).status_code == 200

    renamed = await mo.patch(f"/api/diets/{paleo}", json={"name": "  Paleolithic "})
    assert renamed.status_code == 200, renamed.text
    assert (renamed.json()["id"], renamed.json()["name"]) == (paleo, "Paleolithic")
    diets = await _diets(client)
    assert "Paleolithic" in diets and "Paleo" not in diets
    # The same tag, so the recipe has it under its new name.
    assert await _tags_of(client, cake) == ["Paleolithic"]

    # What it avoids comes with it.
    dairy_free = diets["Dairy-Free"]["id"]
    again = await mo.patch(f"/api/diets/{dairy_free}", json={"name": "Dairy free"})
    assert again.json()["avoids"] == ["milk"]
    # Its own name in other capitals is a change, not a clash.
    capitals = await mo.patch(f"/api/diets/{dairy_free}", json={"name": "Dairy Free"})
    assert capitals.status_code == 200 and capitals.json()["name"] == "Dairy Free"


async def test_a_rename_is_refused(people, client) -> None:
    mo, co = await people("mo", role="moderator"), await people("co", role="contributor")
    diets = await _diets(client)
    paleo = diets["Paleo"]["id"]
    clash = await mo.patch(f"/api/diets/{paleo}", json={"name": "vegan"})
    assert clash.status_code == 409 and "Vegan" in clash.json()["detail"]
    assert (await mo.patch(f"/api/diets/{paleo}", json={"name": " "})).status_code == 422
    assert (await mo.patch(f"/api/diets/{paleo}", json={"name": "x" * 61})).status_code == 422
    # A course is a tag, and not a diet.
    dessert = await _tag(client, "course", "Dessert")
    assert (await mo.patch(f"/api/diets/{dessert}", json={"name": "Pudding"})).status_code == 404
    assert (await co.patch(f"/api/diets/{paleo}", json={"name": "Stone Age"})).status_code == 403
    assert (await client.patch(f"/api/diets/{paleo}", json={"name": "Stone Age"})).status_code in (
        401,
        403,
    )
    assert "Paleo" in await _diets(client)


async def test_a_diet_is_removed_from_everything_tagged_with_it(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book, edition = await _book(mo, adb)
    cake = await _recipe(mo, book, edition, "Rhubarb Cake")
    fool = await _recipe(mo, book, edition, "Rhubarb Fool")
    made = await mo.post("/api/diets", json={"name": "Whole30", "allergens": ["milk"]})
    diet = made.json()["id"]
    dessert = await _tag(client, "course", "Dessert")
    for recipe in (cake, fool):
        r = await mo.put(f"/api/recipes/{recipe}/tags", json={"tags": [diet, dessert]})
        assert r.status_code == 200, r.text
    assert (await mo.put(f"/api/sources/{book}/tags", json={"tags": [diet]})).status_code == 200

    use = await mo.get(f"/api/diets/{diet}/use")
    assert use.json() == {"recipes": 2, "sources": 1, "swaps": 0, "swap_ingredients": []}

    gone = await mo.delete(f"/api/diets/{diet}")
    assert gone.status_code == 204, gone.text
    assert "Whole30" not in await _diets(client)
    assert await _tags_of(client, cake) == ["Dessert"]
    assert (await client.get(f"/api/sources/{book}")).json()["tags"] == []
    assert (
        await adb.scalar(
            text("SELECT count(*) FROM diet_allergens WHERE diet_tag_id = :d"), {"d": diet}
        )
        == 0
    )
    assert (await mo.delete(f"/api/diets/{diet}")).status_code == 404
    assert (await mo.get(f"/api/diets/{diet}/use")).status_code == 404


async def test_a_removal_is_undone_from_recent_changes(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book, edition = await _book(mo, adb)
    cake = await _recipe(mo, book, edition, "Rhubarb Cake")
    diet = (await mo.post("/api/diets", json={"name": "Whole30", "allergens": ["milk"]})).json()[
        "id"
    ]
    await mo.put(f"/api/recipes/{cake}/tags", json={"tags": [diet]})
    assert (await mo.delete(f"/api/diets/{diet}")).status_code == 204

    changes = (await mo.get("/api/changes")).json()
    [removal] = [
        c
        for c in changes
        if any(e["table"] == "tags" and e["action"] == "removed" for e in c["entries"])
    ]
    # One save: the diet, what it avoided and where it was, to undo whole.
    assert sorted(e["table"] for e in removal["entries"]) == [
        "diet_allergens",
        "recipe_tags",
        "tags",
    ]
    undone = await mo.post(f"/api/changes/{removal['id']}/revert")
    assert undone.status_code == 200, undone.text
    back = (await _diets(client))["Whole30"]
    assert (back["id"], back["avoids"]) == (diet, ["milk"])
    assert await _tags_of(client, cake) == ["Whole30"]


async def test_a_diet_with_a_swap_stays(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book, edition = await _book(mo, adb)
    await _recipe(mo, book, edition, "Shortbread", ("Butter", "Margarine"))
    butter, margarine = [
        str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": n}))
        for n in ("Butter", "Margarine")
    ]
    dairy_free = (await _diets(client))["Dairy-Free"]["id"]
    swap = await mo.post(
        "/api/substitutions",
        json={
            "instead_of": {"ingredient_id": butter},
            "use": {"ingredient_id": margarine},
            "diet_id": dairy_free,
        },
    )
    assert swap.status_code == 201, swap.text

    use = (await mo.get(f"/api/diets/{dairy_free}/use")).json()
    assert use["swaps"] == 1
    assert use["swap_ingredients"] == [{"kind": "ingredient", "id": butter, "name": "Butter"}]
    refused = await mo.delete(f"/api/diets/{dairy_free}")
    assert refused.status_code == 409
    assert refused.json()["detail"] == "1 swap is recorded for Dairy-Free. Remove those first."
    assert "Dairy-Free" in await _diets(client)

    # With the swap gone, so may the diet be.
    assert (await mo.delete(f"/api/substitutions/{swap.json()['id']}")).status_code == 204
    assert (await mo.delete(f"/api/diets/{dairy_free}")).status_code == 204


async def test_only_a_moderator_removes_and_only_a_diet(people, client) -> None:
    mo, co = await people("mo", role="moderator"), await people("co", role="contributor")
    paleo = (await _diets(client))["Paleo"]["id"]
    assert (await co.delete(f"/api/diets/{paleo}")).status_code == 403
    assert (await co.get(f"/api/diets/{paleo}/use")).status_code == 403
    assert (await client.delete(f"/api/diets/{paleo}")).status_code in (401, 403)
    assert (await client.get(f"/api/diets/{paleo}/use")).status_code in (401, 403)
    dessert = await _tag(client, "course", "Dessert")
    assert (await mo.delete(f"/api/diets/{dessert}")).status_code == 404
    assert "Paleo" in await _diets(client)
    assert await _tag(client, "course", "Dessert") == dessert


async def test_a_familys_own_recipes_arent_counted_and_lose_it_too(people, client) -> None:
    """The number asked for before removing says nothing of what a family
    has tagged; the tag goes from theirs as from the catalog's."""
    mo, ann = await people("mo", role="moderator"), await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Secret Box", "acknowledged": True})
    ).json()["id"]
    stew = (await ann.post(f"/api/sources/{box}/recipes", json={"title": "Secret Stew"})).json()[
        "id"
    ]
    paleo = (await _diets(client))["Paleo"]["id"]
    tagged = await ann.put(f"/api/recipes/{stew}/tags", json={"tags": [paleo]})
    assert tagged.status_code == 200, tagged.text

    use = (await mo.get(f"/api/diets/{paleo}/use")).json()
    assert (use["recipes"], use["sources"]) == (0, 0)
    assert (await mo.delete(f"/api/diets/{paleo}")).status_code == 204
    assert [t["name"] for t in (await ann.get(f"/api/recipes/{stew}")).json()["tags"]] == []

    # What the moderator is shown of the change says nothing of the family's
    # recipe. And it can't be undone: a change that touched a family's
    # collection is the family's (routers/history.py), so Admin says before
    # removing that this is when undoing won't work.
    [removal] = [
        c
        for c in (await mo.get("/api/changes")).json()
        if any(e["table"] == "tags" and e["action"] == "removed" for e in c["entries"])
    ]
    assert [e["table"] for e in removal["entries"]] == ["tags"]
    assert "Secret" not in str(removal)
    assert (await mo.post(f"/api/changes/{removal['id']}/revert")).status_code == 404
    assert "Paleo" not in await _diets(client)
