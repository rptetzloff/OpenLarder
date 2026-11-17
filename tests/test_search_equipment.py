"""Search by equipment (routers/search.py): `needs` keeps the recipes that
need a thing, `no_equipment` leaves out the ones that can't do without it,
and each hit says what it needs. *Ray's equipment spec, 2026-11-15.*"""

import uuid

import pytest
from sqlalchemy import text

from openlarder.routers import search

# What each recipe is recorded as needing; None is "nothing special", and a
# recipe that isn't here at all has nothing recorded.
NEEDS = {
    "Kit Ice Cream": ["ice cream maker"],
    "Kit Cake": ["stand mixer or hand mixer", "9-inch springform pan"],
    "Kit Meringue": ["stand mixer"],
    "Kit Mousse": ["stand mixer or food processor"],
    "Kit Stir-fry": ["wok"],
    "Kit Salad": None,
}
EVERY = sorted([*NEEDS, "Kit Toast"])


@pytest.fixture
async def mo(people):
    return await people("mo", role="moderator")


@pytest.fixture
async def book(mo, adb) -> str:
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": []})).json()[
        "id"
    ]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    for title in EVERY:
        body = {"title": title, "editions": [{"edition_id": edition}], "ingredients": ["eggs"]}
        if title in NEEDS:
            body |= (
                {"nothing_special": True} if NEEDS[title] is None else {"equipment": NEEDS[title]}
            )
        made = await mo.post(f"/api/sources/{book}/recipes", json=body)
        assert made.status_code == 201, made.text
    return book


async def _thing(adb, name: str) -> str:
    return str(await adb.scalar(text("SELECT id FROM equipment WHERE name = :n"), {"n": name}))


async def _found(c, **params) -> dict:
    response = await c.get("/api/search", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _titles(found: dict) -> list[str]:
    assert found["total"] == len(found["recipes"])
    return sorted(r["title"] for r in found["recipes"])


async def test_needs_finds_what_can_be_made_with_a_thing(client, book, adb) -> None:
    maker = await _thing(adb, "Ice cream maker")
    found = await _found(client, needs=maker)
    # Enough to search by, by itself: "what can I make with my ice cream maker?"
    assert _titles(found) == ["Kit Ice Cream"]
    assert found["needing"] == [{"id": maker, "name": "Ice cream maker"}]
    assert found["no_equipment"] == [] and found["missing_equipment"] == []
    # A need is met by any of its choices, and by what counts as the thing
    # asked for: a stand mixer is a mixer, and so is a hand mixer.
    stand, hand, mixer = [await _thing(adb, n) for n in ("Stand mixer", "Hand mixer", "Mixer")]
    mixed = ["Kit Cake", "Kit Meringue", "Kit Mousse"]
    assert _titles(await _found(client, needs=stand)) == mixed
    assert _titles(await _found(client, needs=mixer)) == mixed
    assert _titles(await _found(client, needs=hand)) == ["Kit Cake"]
    # Several: recipes needing every one.
    pan = await _thing(adb, "Springform pan")
    both = await _found(client, needs=[mixer, pan])
    assert _titles(both) == ["Kit Cake"]
    assert [n["name"] for n in both["needing"]] == ["Mixer", "Springform pan"]
    assert _titles(await _found(client, needs=[maker, pan])) == []
    # With the rest of a search: title words, and ingredients that rank.
    assert _titles(await _found(client, needs=mixer, q="cake")) == ["Kit Cake"]
    eggs = str(await adb.scalar(text("SELECT id FROM ingredients WHERE match_key = 'egg'")))
    ranked = await _found(client, needs=mixer, ingredient=eggs)
    assert _titles(ranked) == mixed and ranked["recipes"][0]["lines"] == 1


async def test_no_equipment_leaves_out_what_cant_do_without_it(client, book, adb) -> None:
    stand, mixer = await _thing(adb, "Stand mixer"), await _thing(adb, "Mixer")
    # Not something to search by: it only takes away.
    alone = await client.get("/api/search", params={"no_equipment": stand})
    assert alone.status_code == 422
    # The meringue has no other way. The cake offers a hand mixer and the
    # mousse a food processor; what's unrecorded, or needs nothing, stays.
    found = await _found(client, q="kit", no_equipment=stand)
    assert _titles(found) == [t for t in EVERY if t != "Kit Meringue"]
    assert found["no_equipment"] == [{"id": stand, "name": "Stand mixer"}]
    # Without any mixer the cake's two choices are both gone.
    without = _titles(await _found(client, q="kit", no_equipment=mixer))
    assert without == [t for t in EVERY if t not in ("Kit Meringue", "Kit Cake")]
    # Several: none of them.
    wok = await _thing(adb, "Wok")
    fewer = _titles(await _found(client, q="kit", no_equipment=[mixer, wok]))
    assert fewer == [t for t in without if t != "Kit Stir-fry"]
    # Both filters together.
    assert _titles(await _found(client, needs=mixer, no_equipment=stand)) == [
        "Kit Cake",
        "Kit Mousse",
    ]


async def test_each_hit_says_what_it_needs(client, book) -> None:
    said = {r["title"]: r["equipment"] for r in (await _found(client, q="kit"))["recipes"]}
    assert said == {
        "Kit Ice Cream": ["Ice cream maker"],
        "Kit Cake": ["Stand mixer or Hand mixer", "9-inch Springform pan"],
        "Kit Meringue": ["Stand mixer"],
        "Kit Mousse": ["Stand mixer or Food processor"],
        "Kit Stir-fry": ["Wok"],
        "Kit Salad": [],
        "Kit Toast": [],
    }


async def test_equipment_thats_gone_or_hidden_is_reported(people, client, book, adb) -> None:
    gone = str(uuid.uuid4())
    wok = await _thing(adb, "Wok")
    # Nothing left to search by: no recipes, and the link's id reported.
    nothing = await _found(client, needs=gone)
    assert nothing["recipes"] == [] and nothing["missing_equipment"] == [gone]
    # One that's there still searches.
    some = await _found(client, needs=[gone, wok], no_equipment=gone)
    assert _titles(some) == ["Kit Stir-fry"] and some["missing_equipment"] == [gone]
    # A thing a family's recipe brought in is theirs: it's found for them,
    # and for anyone else it's one that's gone, moderators included.
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    made = await ann.post(
        f"/api/sources/{box}/recipes",
        json={"title": "Nana's", "ingredients": ["eggs"], "equipment": ["moonbeam press"]},
    )
    assert made.status_code == 201, made.text
    press = await _thing(adb, "Moonbeam press")
    hers = await _found(ann, needs=press)
    assert _titles(hers) == ["Nana's"] and hers["needing"][0]["name"] == "Moonbeam press"
    for other in (client, await people("mo2", role="moderator")):
        theirs = await _found(other, needs=press)
        assert theirs["recipes"] == [] and theirs["needing"] == []
        assert theirs["missing_equipment"] == [press]
        assert "Moonbeam" not in str(await _found(other, q="kit", no_equipment=press))


async def test_a_search_takes_so_much_equipment(client, book) -> None:
    many = [str(uuid.uuid4()) for _ in range(search.MAX_EQUIPMENT + 1)]
    for param in ("needs", "no_equipment"):
        over = await client.get("/api/search", params={"q": "kit", param: many})
        assert over.status_code == 422 and "equipment" in over.json()["detail"], param
        under = await client.get("/api/search", params={"q": "kit", param: many[:-1]})
        assert under.status_code == 200, param


async def _offered(c, q: str, **params) -> dict[str, int]:
    """What the search page's boxes offer for what's typed, in order, each
    with its count."""
    response = await c.get("/api/equipment", params={"q": q, "under": "true", **params})
    assert response.status_code == 200, response.text
    return {e["name"]: e["recipes"] for e in response.json()["equipment"]}


async def test_a_box_counts_what_choosing_a_thing_finds(people, client, book, adb) -> None:
    """It counted the recipes needing exactly that thing, so "Mixer" said 0
    recipes and found three."""
    offered = await _offered(client, "mixer")
    # A mixer's are the stand mixer's and the hand mixer's, each recipe
    # once (the cake offers both); and the most found comes first, where by
    # the recipes naming it the mixer came last.
    assert offered == {"Mixer": 3, "Stand mixer": 3, "Hand mixer": 1}
    assert list(offered) == ["Mixer", "Stand mixer", "Hand mixer"]
    for name, count in offered.items():
        found = await _found(client, needs=await _thing(adb, name))
        assert found["total"] == count, name
    # Without it, the list is as it was: the recipes naming each.
    exact = (await client.get("/api/equipment", params={"q": "mixer"})).json()["equipment"]
    assert {e["name"]: e["recipes"] for e in exact} == {
        "Stand mixer": 3,
        "Hand mixer": 1,
        "Mixer": 0,
    }
    # A family's recipe is counted for them and for nobody else.
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    made = await ann.post(
        f"/api/sources/{box}/recipes",
        json={"title": "Nana's", "ingredients": ["eggs"], "equipment": ["hand mixer"]},
    )
    assert made.status_code == 201, made.text
    assert await _offered(ann, "mixer") == {"Mixer": 4, "Stand mixer": 3, "Hand mixer": 2}
    for other in (client, await people("mo3", role="moderator")):
        assert await _offered(other, "mixer") == offered
