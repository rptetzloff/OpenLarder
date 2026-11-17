"""A recipe's page says which of its needs the viewer hasn't the equipment
for (routers/recipes.py, NeedOut.have): "You don't have this". *Ray's
equipment spec, 2026-11-15.* What they have is their lists'
(routers/equipment_lists.py)."""

import pytest
from sqlalchemy import text

LISTS = "/api/equipment-lists"
NEEDS = ["stand mixer or hand mixer", "ice cream maker", "mixer", "9-inch springform pan"]


@pytest.fixture
async def recipe(people, adb) -> str:
    mo = await people("mo", role="moderator")
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": []})).json()[
        "id"
    ]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    made = await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Baked Alaska",
            "editions": [{"edition_id": edition}],
            "ingredients": ["eggs"],
            "equipment": NEEDS,
        },
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def _list(c, name="Kitchen") -> str:
    r = await c.post(f"{LISTS}/lists", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _item(c, list_id, name, **more) -> str:
    r = await c.post(f"{LISTS}/lists/{list_id}/items", json={"name": name, **more})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _have(c, recipe: str) -> list[bool | None]:
    r = await c.get(f"/api/recipes/{recipe}")
    assert r.status_code == 200, r.text
    return [need["have"] for need in r.json()["equipment"]]


NOTHING_SAID = [None, None, None, None]


async def test_nothing_is_said_until_they_have_said_what_they_have(people, client, recipe) -> None:
    ann = await people("ann")
    assert await _have(client, recipe) == NOTHING_SAID
    assert await _have(ann, recipe) == NOTHING_SAID
    # A list with nothing on it, then with something wanted and something
    # nothing matches: still nothing she has.
    kitchen = await _list(ann)
    assert await _have(ann, recipe) == NOTHING_SAID
    maker = await _item(ann, kitchen, "Ice cream maker", state="want")
    await _item(ann, kitchen, "Nana's springform")
    assert await _have(ann, recipe) == NOTHING_SAID
    # With one thing had, every need is hers or it isn't.
    await _item(ann, kitchen, "Wok")
    assert await _have(ann, recipe) == [False, False, False, False]
    await ann.patch(f"{LISTS}/items/{maker}", json={"state": "have"})
    assert await _have(ann, recipe) == [False, True, False, False]


async def test_a_need_is_met_by_a_choice_or_by_what_counts_as_it(people, client, recipe) -> None:
    ann, bo = await people("ann"), await people("bo")
    kitchen = await _list(ann)
    mixer = await _item(ann, kitchen, "Stand mixer")
    # "Stand mixer or Hand mixer" by its first choice, and "Mixer" because
    # a stand mixer is one; the maker and the pan she hasn't.
    assert await _have(ann, recipe) == [True, False, True, False]
    # A pan by another name for it; the size beside it is set aside.
    await _item(ann, kitchen, "9-inch springform tin")
    assert await _have(ann, recipe) == [True, False, True, True]
    # A mixer alone isn't a stand mixer: it meets only its own need.
    await ann.delete(f"{LISTS}/items/{mixer}")
    await _item(ann, kitchen, "Mixer")
    assert await _have(ann, recipe) == [False, False, True, True]
    # The need's second choice meets it as its first does.
    await _item(ann, kitchen, "Hand mixer")
    assert await _have(ann, recipe) == [True, False, True, True]
    # Hers alone: nobody else is told, signed in or out.
    assert await _have(bo, recipe) == NOTHING_SAID
    assert await _have(client, recipe) == NOTHING_SAID


async def test_a_shared_list_counts_and_a_thing_she_cant_see_doesnt(people, recipe, adb) -> None:
    from test_groups import _group, _join

    ann, bob, dee = await people("ann"), await people("bob"), await people("dee")
    group = await _group(ann)
    await _join(bob, ann, group, "view")
    kitchen = await _list(ann, "Family kitchen")
    await _item(ann, kitchen, "Ice cream maker")
    assert await _have(bob, recipe) == NOTHING_SAID
    await ann.put(f"{LISTS}/lists/{kitchen}/groups", json={"groups": [group]})
    assert await _have(bob, recipe) == [False, True, False, False]
    # Linked, however it came to be, to a thing she can't see: it's nothing
    # of hers, so there's still nothing to go by.
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    made = await ann.post(
        f"/api/sources/{box}/recipes",
        json={"title": "Nana's", "ingredients": ["eggs"], "equipment": ["moonbeam press"]},
    )
    assert made.status_code == 201, made.text
    press = await adb.scalar(text("SELECT id FROM equipment WHERE name = 'Moonbeam press'"))
    hers = await _item(dee, await _list(dee), "Moonbeam press")
    await adb.execute(
        text("UPDATE equipment_list_items SET equipment_id = :e WHERE id = :i"),
        {"e": press, "i": hers},
    )
    assert await _have(dee, recipe) == NOTHING_SAID
    # And the family's own recipe says it of the press for its owner.
    await _item(ann, kitchen, "Moonbeam press")
    assert await _have(ann, made.json()["id"]) == [True]
