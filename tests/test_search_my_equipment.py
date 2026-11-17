"""Search kept to what someone has the equipment for (routers/search.py,
`equipment=mine`): what their lists hold, what's left out, and where the
recipes nobody has recorded equipment for go. *Ray's equipment spec,
2026-11-15; lists as the larder's, Ray, 2026-11-16.*"""

import pytest
from sqlalchemy import text

from openlarder.routers import search

LISTS = "/api/equipment-lists"
# What each recipe is recorded as needing; None is "nothing special", and
# "Kit Toast" has nothing recorded.
NEEDS = {
    "Kit Ice Cream": ["ice cream maker"],
    "Kit Cake": ["stand mixer or hand mixer", "9-inch springform pan"],
    "Kit Meringue": ["stand mixer"],
    "Kit Mousse": ["hand mixer or food processor"],
    "Kit Dough": ["mixer"],
    "Kit Stir-fry": ["wok"],
    "Kit Salad": None,
}
EVERY = sorted([*NEEDS, "Kit Toast"])


@pytest.fixture
async def mo(people):
    return await people("mo", role="moderator")


@pytest.fixture
async def book(mo, adb) -> dict[str, str]:
    """The book's recipes, by title."""
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": []})).json()[
        "id"
    ]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    made = {}
    for title in EVERY:
        body = {"title": title, "editions": [{"edition_id": edition}], "ingredients": ["eggs"]}
        if title in NEEDS:
            body |= (
                {"nothing_special": True} if NEEDS[title] is None else {"equipment": NEEDS[title]}
            )
        r = await mo.post(f"/api/sources/{book}/recipes", json=body)
        assert r.status_code == 201, r.text
        made[title] = r.json()["id"]
    return made


async def _list(c, name="Kitchen") -> str:
    r = await c.post(f"{LISTS}/lists", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _item(c, list_id, name, **more) -> str:
    r = await c.post(f"{LISTS}/lists/{list_id}/items", json={"name": name, **more})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _found(c, **params) -> dict:
    r = await c.get("/api/search", params={"equipment": "mine", **params})
    assert r.status_code == 200, r.text
    return r.json()


def _titles(found: dict) -> list[str]:
    assert found["total"] == len(found["recipes"])
    return sorted(r["title"] for r in found["recipes"])


def _without(*titles: str) -> list[str]:
    return [t for t in EVERY if t not in titles]


async def test_only_what_they_have_the_equipment_for(people, client, book) -> None:
    ann = await people("ann")
    assert (await client.get("/api/search", params={"equipment": "mine"})).status_code == 401
    assert (await ann.get("/api/search", params={"equipment": "theirs"})).status_code == 422
    # With nothing, what needs anything is out; what needs nothing special,
    # and what nobody has recorded, stay.
    bare = await _found(ann, q="kit")
    assert (_titles(bare), bare["equipment_items"]) == (["Kit Salad", "Kit Toast"], 0)
    kitchen = await _list(ann)
    await _item(ann, kitchen, "Stand mixer")
    wok = await _item(ann, kitchen, "Wok")
    found = await _found(ann, q="kit")
    # A stand mixer meets "Stand mixer", and "Mixer", which it counts as;
    # it doesn't meet "Hand mixer or Food processor", nor the cake's pan.
    assert _titles(found) == _without("Kit Ice Cream", "Kit Cake", "Kit Mousse")
    assert found["equipment_items"] == 2
    # Enough to search by, by itself, as a larder is.
    assert _titles(await _found(ann)) == _titles(found)
    # Something wanted isn't had, nor is something nothing matches.
    maker = await _item(ann, kitchen, "Ice cream maker", state="want")
    await _item(ann, kitchen, "Nana's springform")
    assert _titles(await _found(ann, q="kit")) == _titles(found)
    assert (await _found(ann, q="kit"))["equipment_items"] == 2
    await ann.patch(f"{LISTS}/items/{maker}", json={"state": "have"})
    pan = await _item(ann, kitchen, "Springform tin")
    assert _titles(await _found(ann, q="kit")) == _without("Kit Mousse")
    # And taken away again.
    assert (await ann.delete(f"{LISTS}/items/{wok}")).status_code == 204
    assert (await ann.delete(f"{LISTS}/items/{pan}")).status_code == 204
    assert _titles(await _found(ann, q="kit")) == _without("Kit Mousse", "Kit Stir-fry", "Kit Cake")


async def test_unrecorded_recipes_stay_come_last_and_are_counted(people, book, adb) -> None:
    ann = await people("ann")
    kitchen = await _list(ann)
    await _item(ann, kitchen, "Wok")
    found = await _found(ann, q="kit")
    assert [r["title"] for r in found["recipes"]] == ["Kit Salad", "Kit Stir-fry", "Kit Toast"]
    assert (found["total"], found["unrecorded"]) == (3, 1)
    assert [r["equipment_recorded"] for r in found["recipes"]] == [True, True, False]
    # However else they're ordered: the best rated first puts it last still.
    for title, spoons in (("Kit Toast", 5), ("Kit Stir-fry", 4)):
        rated = await ann.put(f"/api/recipes/{book[title]}/rating", json={"spoons": spoons})
        assert rated.status_code in (200, 204), rated.text
    by_rating = await _found(ann, q="kit", sort="rating")
    assert [r["title"] for r in by_rating["recipes"]] == ["Kit Stir-fry", "Kit Salad", "Kit Toast"]
    # A recipe with a need listed, and nobody having said the list is
    # whole, is judged on the need it has: recorded, and kept or not by it.
    await adb.execute(
        text("UPDATE recipes SET equipment_checked = false WHERE id IN (:a, :b)"),
        {"a": book["Kit Stir-fry"], "b": book["Kit Meringue"]},
    )
    again = await _found(ann, q="kit")
    assert _titles(again) == ["Kit Salad", "Kit Stir-fry", "Kit Toast"]
    assert again["unrecorded"] == 1
    assert {r["title"]: r["equipment_recorded"] for r in again["recipes"]} == {
        "Kit Salad": True,
        "Kit Stir-fry": True,
        "Kit Toast": False,
    }
    assert again["recipes"][-1]["title"] == "Kit Toast"
    # Without the filter nothing is counted, and nothing put last.
    plain = (await ann.get("/api/search", params={"q": "kit"})).json()
    assert (plain["unrecorded"], plain["equipment_items"]) == (None, None)
    # The toast, rated best, leads a search for a title; kept to her
    # equipment, it was last.
    assert plain["recipes"][0]["title"] == "Kit Toast" and _titles(plain) == sorted(EVERY)
    assert {r["title"] for r in plain["recipes"] if not r["equipment_recorded"]} == {"Kit Toast"}
    # And with ingredients, which rank. Every recipe here is all eggs, so
    # they'd come by title: named to come first, the one unrecorded is last.
    await adb.execute(
        text("UPDATE recipes SET title = 'Kit Aardvark Toast' WHERE id = :r"),
        {"r": book["Kit Toast"]},
    )
    eggs = str(await adb.scalar(text("SELECT id FROM ingredients WHERE match_key = 'egg'")))
    ranked = await _found(ann, ingredient=eggs)
    assert [r["title"] for r in ranked["recipes"]] == [
        "Kit Salad",
        "Kit Stir-fry",
        "Kit Aardvark Toast",
    ]
    assert (ranked["total"], ranked["unrecorded"], ranked["recipes"][0]["lines"]) == (3, 1, 1)
    unfiltered = (await ann.get("/api/search", params={"ingredient": eggs})).json()
    assert unfiltered["recipes"][0]["title"] == "Kit Aardvark Toast"


async def test_it_narrows_to_lists_things_or_less_some(people, book) -> None:
    ann = await people("ann")
    kitchen, cabin = await _list(ann, "Kitchen"), await _list(ann, "Cabin")
    mixer = await _item(ann, kitchen, "Stand mixer")
    maker = await _item(ann, kitchen, "Ice cream maker")
    wok = await _item(ann, cabin, "Wok")
    everything = _without("Kit Cake", "Kit Mousse")
    assert _titles(await _found(ann, q="kit")) == everything
    at_the_cabin = await _found(ann, q="kit", equipment_list=[cabin])
    assert (_titles(at_the_cabin), at_the_cabin["equipment_items"]) == (
        ["Kit Salad", "Kit Stir-fry", "Kit Toast"],
        1,
    )
    assert _titles(await _found(ann, q="kit", equipment_list=[cabin, kitchen])) == everything
    only = await _found(ann, q="kit", equipment_item=[maker])
    assert _titles(only) == ["Kit Ice Cream", "Kit Salad", "Kit Toast"]
    # Only-these wins over lists.
    assert _titles(await _found(ann, q="kit", equipment_item=[maker], equipment_list=[cabin])) == (
        _titles(only)
    )
    less = await _found(ann, q="kit", equipment_without=[mixer, wok])
    assert (_titles(less), less["equipment_items"]) == (_titles(only), 1)
    many = [mixer] * (search.MAX_LARDER_PICKS + 1)
    over = await ann.get("/api/search", params={"equipment": "mine", "equipment_item": many})
    assert over.status_code == 422 and "equipment things" in over.json()["detail"]


async def test_a_shared_list_counts_and_someone_elses_doesnt(people, book) -> None:
    from test_groups import _group, _join

    ann, bob, dee = await people("ann"), await people("bob"), await people("dee")
    group = await _group(ann)
    await _join(bob, ann, group, "view")
    kitchen = await _list(ann, "Family kitchen")
    wok = await _item(ann, kitchen, "Wok")
    assert _titles(await _found(bob, q="kit")) == ["Kit Salad", "Kit Toast"]
    await ann.put(f"{LISTS}/lists/{kitchen}/groups", json={"groups": [group]})
    shared = await _found(bob, q="kit")
    assert (_titles(shared), shared["equipment_items"]) == (
        ["Kit Salad", "Kit Stir-fry", "Kit Toast"],
        1,
    )
    # Naming a list or a thing that isn't hers to see gets a stranger nothing.
    for narrowed in ({"equipment_list": [kitchen]}, {"equipment_item": [wok]}):
        theirs = await _found(dee, q="kit", **narrowed)
        assert (_titles(theirs), theirs["equipment_items"]) == (["Kit Salad", "Kit Toast"], 0)


async def test_with_the_other_equipment_filters(people, book, adb) -> None:
    ann = await people("ann")
    kitchen = await _list(ann)
    await _item(ann, kitchen, "Stand mixer")
    await _item(ann, kitchen, "Wok")
    mixer = str(await adb.scalar(text("SELECT id FROM equipment WHERE name = 'Mixer'")))
    wok = str(await adb.scalar(text("SELECT id FROM equipment WHERE name = 'Wok'")))
    # Of what needs a mixer, what she can make; and less what needs a wok.
    assert _titles(await _found(ann, needs=mixer)) == ["Kit Dough", "Kit Meringue"]
    assert _titles(await _found(ann, q="kit", no_equipment=wok)) == _without(
        "Kit Ice Cream", "Kit Cake", "Kit Mousse", "Kit Stir-fry"
    )


async def test_a_thing_she_cant_see_counts_for_nothing(people, book, adb) -> None:
    """Linked, however it came to be, to a thing only someone else's hidden
    recipe brought in: it isn't hers to have."""
    ann, dee = await people("ann"), await people("dee")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    made = await ann.post(
        f"/api/sources/{box}/recipes",
        json={"title": "Kit Nana's", "ingredients": ["eggs"], "equipment": ["moonbeam press"]},
    )
    assert made.status_code == 201, made.text
    press = await adb.scalar(text("SELECT id FROM equipment WHERE name = 'Moonbeam press'"))
    hers = await _item(ann, await _list(ann), "Moonbeam press")
    assert hers and (await _found(ann, q="kit nana"))["equipment_items"] == 1
    assert _titles(await _found(ann, q="kit nana")) == ["Kit Nana's"]
    theirs = await _item(dee, await _list(dee), "Moonbeam press")
    await adb.execute(
        text("UPDATE equipment_list_items SET equipment_id = :e WHERE id = :i"),
        {"e": press, "i": theirs},
    )
    found = await _found(dee, q="kit")
    assert (found["equipment_items"], _titles(found)) == (0, ["Kit Salad", "Kit Toast"])
