"""What a recipe needs (needs.py): reading a need as typed, saving a
recipe's, the three states, and who sees a thing a recipe brought in.
*Ray's equipment spec, 2026-11-15.*"""

import uuid

import pytest
from sqlalchemy import text

from openlarder import needs


@pytest.fixture
async def mo(people):
    return await people("mo", role="moderator")


async def _book(c, title="Cakes") -> str:
    made = await c.post("/api/sources/manual", json={"title": title, "authors": ["Ann Author"]})
    assert made.status_code == 200, made.text
    return made.json()["id"]


async def _body(c, source: str, title: str, **more) -> dict:
    editions = (await c.get(f"/api/sources/{source}")).json()["editions"]
    body = {"title": title, "ingredients": ["Egg"], **more}
    if editions:
        body["editions"] = [{"edition_id": editions[0]["id"], "page": "1"}]
    return body


async def _recipe(c, source: str, title: str, **more) -> str:
    made = await c.post(
        f"/api/sources/{source}/recipes", json=await _body(c, source, title, **more)
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def _shown(c, recipe: str) -> dict:
    response = await c.get(f"/api/recipes/{recipe}")
    assert response.status_code == 200, response.text
    return response.json()


def _needs(shown: dict) -> list[tuple[str | None, list[str]]]:
    return [(n["detail"], [o["name"] for o in n["options"]]) for n in shown["equipment"]]


# Reading a need


@pytest.mark.parametrize(
    ("typed", "detail", "names"),
    [
        ("stand mixer", None, ["stand mixer"]),
        ("Stand mixer or hand mixer", None, ["Stand mixer", "hand mixer"]),
        ("9-inch springform pan", "9-inch", ["springform pan"]),
        ("9 inch springform pan", "9 inch", ["springform pan"]),
        ('9" springform pan', '9"', ["springform pan"]),
        ("9 x 13 inch baking pan", "9 x 13 inch", ["baking pan"]),
        ("9x13-inch pan", "9x13-inch", ["pan"]),
        ("10- to 12-inch cast-iron skillet", "10- to 12-inch", ["cast-iron skillet"]),
        ("6-quart Dutch oven", "6-quart", ["Dutch oven"]),
        ("1½-quart saucepan", "1½-quart", ["saucepan"]),
        ("23cm tart tin", "23cm", ["tart tin"]),
        ("springform pan, 9-inch", "9-inch", ["springform pan"]),
        ("springform pan (9-inch)", "9-inch", ["springform pan"]),
        ("a 9-inch springform pan or 9-inch cake pan", "9-inch", ["springform pan", "cake pan"]),
        ("  an   ice cream maker ", None, ["ice cream maker"]),
        ("stand mixer or Stand Mixers", None, ["stand mixer"]),
        # Not sizes: a number that is part of a name, a unit inside a word.
        ("2-piece tube pan", None, ["2-piece tube pan"]),
        ("9 inchworm molds", None, ["9 inchworm molds"]),
    ],
)
def test_a_need_is_read_as_typed(typed, detail, names) -> None:
    read = needs.read(typed)
    assert (read.detail, read.names) == (detail, names)


def test_an_empty_box_is_no_need() -> None:
    assert needs.read("   ") is None


@pytest.mark.parametrize(
    ("typed", "why"),
    [
        ("9-inch", "is a size"),
        ("stand mixer or 6-quart", "is a size"),
        ("stand mixer or ...", "doesn't name anything"),
        ("a or b or c or d or e or f or g", "at most 6 things"),
        ("x" * 151, "at most 150 characters"),
    ],
)
def test_what_isnt_a_need_says_why(typed, why) -> None:
    with pytest.raises(needs.Refused) as refused:
        needs.read(typed)
    assert why in str(refused.value)


# Saving a recipe's needs


async def test_a_recipes_needs_are_saved_and_shown_in_order(mo, client, adb) -> None:
    book = await _book(mo)
    cake = await _recipe(
        mo,
        book,
        "Sponge",
        equipment=["Stand mixer or hand mixer", "9-inch springform pan", "kitchen scales"],
    )
    shown = await _shown(client, cake)
    assert shown["equipment_checked"] is True
    # Each matched to the list's own thing, by its name or another name.
    assert _needs(shown) == [
        (None, ["Stand mixer", "Hand mixer"]),
        ("9-inch", ["Springform pan"]),
        (None, ["Kitchen scale"]),
    ]
    # And as the edit form takes each back.
    assert [n["text"] for n in shown["equipment"]] == [
        "Stand mixer or Hand mixer",
        "9-inch Springform pan",
        "Kitchen scale",
    ]
    listed = {
        e["name"]: e["recipes"] for e in (await client.get("/api/equipment")).json()["equipment"]
    }
    assert (listed["Stand mixer"], listed["Springform pan"], listed["Wok"]) == (1, 1, 0)
    assert list(listed)[:4] == ["Hand mixer", "Kitchen scale", "Springform pan", "Stand mixer"]


async def test_three_states_and_never_two(mo, client) -> None:
    """Ray's spec: a recipe nobody has touched says "not recorded yet",
    never "no special equipment"."""
    book = await _book(mo)
    untouched = await _recipe(mo, book, "Sponge")
    shown = await _shown(client, untouched)
    assert (shown["equipment_checked"], shown["equipment"]) == (False, [])

    nothing = await _recipe(mo, book, "Toast", nothing_special=True)
    shown = await _shown(client, nothing)
    assert (shown["equipment_checked"], shown["equipment"]) == (True, [])

    needing = await _recipe(mo, book, "Ice Cream", equipment=["ice cream maker"])
    shown = await _shown(client, needing)
    assert shown["equipment_checked"] is True and _needs(shown) == [(None, ["Ice cream maker"])]

    # Saying both is refused: which is it?
    both = await mo.post(
        f"/api/sources/{book}/recipes",
        json=await _body(mo, book, "Waffles", equipment=["waffle iron"], nothing_special=True),
    )
    assert both.status_code == 422 and "Nothing special" in both.json()["detail"]


async def test_a_save_that_doesnt_speak_of_equipment_leaves_it_be(mo, client, adb) -> None:
    """Bulk entry and a suggested change send a recipe without it."""
    book = await _book(mo)
    cake = await _recipe(mo, book, "Sponge", equipment=["stand mixer", "bundt pan"])
    before = await adb.scalar(text("SELECT max(id) FROM revisions"))
    changed = await mo.put(f"/api/recipes/{cake}", json=await _body(mo, book, "Sponge Cake"))
    assert changed.status_code == 200, changed.text
    shown = await _shown(client, cake)
    assert shown["title"] == "Sponge Cake" and shown["equipment_checked"] is True
    assert _needs(shown) == [(None, ["Stand mixer"]), (None, ["Bundt pan"])]
    # Nor does saving the same needs again write them again.
    same = await _body(mo, book, "Sponge Cake", equipment=["Stand mixer", "a bundt pan"])
    assert (await mo.put(f"/api/recipes/{cake}", json=same)).status_code == 200
    rewritten = await adb.scalar(
        text(
            "SELECT count(*) FROM revisions WHERE id > :b AND table_name IN"
            " ('recipe_equipment', 'equipment_options')"
        ),
        {"b": before},
    )
    assert rewritten == 0


async def test_needs_are_changed_and_taken_away(mo, client) -> None:
    book = await _book(mo)
    cake = await _recipe(mo, book, "Sponge", equipment=["stand mixer", "bundt pan"])
    fewer = await _body(mo, book, "Sponge", equipment=["8-inch round cake pan", "", "  "])
    assert (await mo.put(f"/api/recipes/{cake}", json=fewer)).status_code == 200
    shown = await _shown(client, cake)
    assert _needs(shown) == [("8-inch", ["Round cake pan"])]
    # An empty list, and nothing said: not recorded, again.
    none = await _body(mo, book, "Sponge", equipment=[])
    assert (await mo.put(f"/api/recipes/{cake}", json=none)).status_code == 200
    shown = await _shown(client, cake)
    assert (shown["equipment_checked"], shown["equipment"]) == (False, [])
    # The same need typed twice is one.
    twice = await _body(mo, book, "Sponge", equipment=["stand mixer", "Stand Mixers"])
    assert (await mo.put(f"/api/recipes/{cake}", json=twice)).status_code == 200
    assert _needs(await _shown(client, cake)) == [(None, ["Stand mixer"])]


async def test_what_any_kitchen_has_is_refused(mo, adb) -> None:
    """Ray's spec: adding "mixing bowl" to a recipe is refused with the
    "expected in any kitchen" message."""
    book = await _book(mo)
    for typed, name in (("mixing bowl", "Mixing bowl"), ("stand mixer or frying pans", "Skillet")):
        refused = await mo.post(
            f"/api/sources/{book}/recipes",
            json=await _body(mo, book, "Sponge", equipment=[typed]),
        )
        assert refused.status_code == 422, typed
        assert refused.json()["detail"] == (
            f"“{name}” is expected in any kitchen, so it isn't recorded."
        )
    # Nothing of the recipe was saved either.
    assert await adb.scalar(text("SELECT count(*) FROM recipes WHERE title = 'Sponge'")) == 0


# A thing the list doesn't have


async def test_a_name_the_list_doesnt_have_makes_a_thing(mo, client, adb) -> None:
    book = await _book(mo)
    cake = await _recipe(mo, book, "Eggs", equipment=["egg coddler or ramekins"])
    shown = await _shown(client, cake)
    assert _needs(shown) == [(None, ["Egg coddler", "Ramekins"])]
    coddler = shown["equipment"][0]["options"][0]["id"]
    row = (
        await adb.execute(
            text("SELECT name, match_key, listed, assumed FROM equipment WHERE id = :i"),
            {"i": uuid.UUID(coddler)},
        )
    ).one()
    assert tuple(row) == ("Egg coddler", "egg coddler", False, False)
    # Its recipe is everyone's, so it is: on its page, and found by name.
    assert (await client.get(f"/api/equipment/{coddler}")).json()["total"] == 1
    found = (await client.get("/api/equipment", params={"q": "coddler"})).json()["equipment"]
    assert [e["name"] for e in found] == ["Egg coddler"]
    # Another recipe naming it, however written, means the same one.
    other = await _recipe(mo, book, "More Eggs", equipment=["Egg Coddlers"])
    assert (await _shown(client, other))["equipment"][0]["options"][0]["id"] == coddler


async def test_a_thing_no_recipe_needs_any_more_is_removed(mo, client, adb) -> None:
    book = await _book(mo)
    cake = await _recipe(mo, book, "Eggs", equipment=["egg coddler", "wok"])
    other = await _recipe(mo, book, "More Eggs", equipment=["egg coddler"])

    async def there() -> int:
        return await adb.scalar(text("SELECT count(*) FROM equipment WHERE name = 'Egg coddler'"))

    # Still needed by one.
    none = await _body(mo, book, "Eggs", nothing_special=True)
    assert (await mo.put(f"/api/recipes/{cake}", json=none)).status_code == 200
    assert await there() == 1
    # By none: gone. What the list has stays, needed or not.
    assert (await mo.delete(f"/api/recipes/{other}")).status_code == 204
    assert await there() == 0
    assert await adb.scalar(text("SELECT count(*) FROM equipment WHERE name = 'Wok'")) == 1


async def test_a_thing_a_private_recipe_brought_in_is_its_owners(people, client, adb) -> None:
    ann, bob = await people("ann"), await people("bob")
    mo = await people("mo", role="moderator")
    box = (
        await ann.post("/api/sources/family", json={"title": "Secret Box", "acknowledged": True})
    ).json()["id"]
    stew = await _recipe(ann, box, "Secret Stew", equipment=["Nana's cauldron", "Dutch oven"])
    cauldron = (await _shown(ann, stew))["equipment"][0]["options"][0]["id"]
    for other in (client, bob, mo):
        assert (await other.get(f"/api/equipment/{cauldron}")).status_code == 404
        assert (await other.get(f"/api/equipment/{cauldron}/history")).status_code == 404
        everything = (await other.get("/api/equipment", params={"assumed": True})).text
        assert "cauldron" not in everything
        assert (await other.get("/api/equipment", params={"q": "cauldron"})).json()["total"] == 0
    # A moderator can't change what they can't see, nor read of it in the
    # latest changes.
    assert (await mo.patch(f"/api/equipment/{cauldron}", json={"name": "Pot"})).status_code == 404
    assert (await mo.delete(f"/api/equipment/{cauldron}")).status_code == 404
    assert "cauldron" not in (await mo.get("/api/changes")).text
    # Its owner sees it, and that her recipe needs it.
    assert (await ann.get(f"/api/equipment/{cauldron}")).json()["total"] == 1
    found = (await ann.get("/api/equipment", params={"q": "cauldron"})).json()["equipment"]
    assert [e["name"] for e in found] == ["Nana's cauldron"]
    # The Dutch oven is the list's, and everyone's; that her recipe needs
    # one is hers.
    dutch = await adb.scalar(text("SELECT id FROM equipment WHERE name = 'Dutch oven'"))
    assert (await client.get(f"/api/equipment/{dutch}")).json()["total"] == 0
    assert (await ann.get(f"/api/equipment/{dutch}")).json()["total"] == 1
    # Deleted with her recipe, without a trace a moderator can read.
    assert (await ann.delete(f"/api/recipes/{stew}")).status_code == 204
    assert await adb.scalar(text("SELECT count(*) FROM equipment WHERE name LIKE 'Nana%'")) == 0
    assert "cauldron" not in (await mo.get("/api/changes")).text


async def test_a_thing_in_a_recipe_waiting_for_review_waits_with_it(people, client) -> None:
    mo = await people("mo", role="moderator")
    con = await people("con", role="contributor")
    book = await _book(mo)
    pie = await _recipe(con, book, "Waiting Pie", equipment=["pie bird"])
    bird = (await _shown(con, pie))["equipment"][0]["options"][0]["id"]
    assert (await client.get(f"/api/equipment/{bird}")).status_code == 404
    # Its maker and a moderator see it, as they see the recipe.
    for who in (con, mo):
        assert (await who.get(f"/api/equipment/{bird}")).json()["name"] == "Pie bird"
    approved = await mo.post(f"/api/review/recipes/{pie}", json={"action": "approve"})
    assert approved.status_code == 200, approved.text
    assert (await client.get(f"/api/equipment/{bird}")).json()["total"] == 1


async def test_a_recipes_needs_are_in_its_history(mo, client) -> None:
    book = await _book(mo)
    cake = await _recipe(mo, book, "Sponge", equipment=["9-inch springform pan"])
    history = (await client.get(f"/api/recipes/{cake}/history")).json()
    entries = [(e["what"], e["action"], e["name"]) for change in history for e in change["entries"]]
    assert ("need", "added", None) in entries or ("need", "added", "9-inch") in entries
    assert [e for e in entries if e[:2] == ("equipment choice", "added")]


# A thing's page lists the recipes that need it


async def test_a_things_page_lists_its_recipes_with_how_each_needs_it(mo, client, adb) -> None:
    book = await _book(mo)
    cake = await _recipe(mo, book, "Sponge", equipment=["Stand mixer or hand mixer"])
    torte = await _recipe(mo, book, "Torte", equipment=["wok", "5-quart stand mixer"])
    rolls = await _recipe(mo, book, "Rolls", equipment=["hand mixer"])
    ids = {
        n: str(await adb.scalar(text("SELECT id FROM equipment WHERE name = :n"), {"n": n}))
        for n in ("Mixer", "Stand mixer", "Hand mixer")
    }
    stand = (await client.get(f"/api/equipment/{ids['Stand mixer']}")).json()
    assert [(r["title"], r["line"]) for r in stand["recipes"]] == [
        ("Sponge", "Stand mixer or Hand mixer"),
        ("Torte", "5-quart Stand mixer"),
    ]
    assert (stand["total"], stand["listed_total"]) == (2, 2)
    assert {r["id"] for r in stand["recipes"]} == {cake, torte}
    # A mixer's own recipes are none; with what counts as it, all three.
    mixer = (await client.get(f"/api/equipment/{ids['Mixer']}")).json()
    assert (mixer["recipes"], mixer["total"], mixer["family_total"]) == ([], 0, 3)
    under = (await client.get(f"/api/equipment/{ids['Mixer']}", params={"under": True})).json()
    assert [(r["title"], r["line"]) for r in under["recipes"]] == [
        ("Rolls", "Hand mixer"),
        ("Sponge", "Stand mixer or Hand mixer"),
        ("Torte", "5-quart Stand mixer"),
    ]
    assert under["listed_total"] == 3 and rolls in {r["id"] for r in under["recipes"]}


# Checking needs as they're typed


async def test_needs_are_checked_as_theyre_typed(mo, client) -> None:
    typed = [
        "stand mixer or stick blender",
        "9-inch springform pan",
        "egg coddler",
        "mixing bowl",
        "9-inch",
        "",
    ]
    read = (await mo.post("/api/equipment/check", json={"needs": typed})).json()
    both, pan, new, bowl, size, empty = read
    assert [(o["name"], o["equipment"]["name"], o["alias"]) for o in both["options"]] == [
        ("stand mixer", "Stand mixer", False),
        ("stick blender", "Immersion blender", True),
    ]
    assert (pan["detail"], pan["options"][0]["equipment"]["name"]) == ("9-inch", "Springform pan")
    assert new["options"] == [{"name": "egg coddler", "equipment": None, "alias": False}]
    assert new["problem"] is None
    assert bowl["problem"] == "“Mixing bowl” is expected in any kitchen, so it isn't recorded."
    assert "is a size" in size["problem"] and size["options"] == []
    assert empty == {"detail": None, "options": [], "problem": None}
    assert (await client.post("/api/equipment/check", json={"needs": typed})).status_code == 401


async def test_checking_doesnt_say_a_hidden_thing_exists(people) -> None:
    ann, bob = await people("ann"), await people("bob")
    box = (
        await ann.post("/api/sources/family", json={"title": "Secret Box", "acknowledged": True})
    ).json()["id"]
    await _recipe(ann, box, "Secret Stew", equipment=["Nana's cauldron"])
    asked = {"needs": ["nana's cauldron"]}
    [hers] = (await ann.post("/api/equipment/check", json=asked)).json()
    assert hers["options"][0]["equipment"]["name"] == "Nana's cauldron"
    [his] = (await bob.post("/api/equipment/check", json=asked)).json()
    assert his["options"] == [{"name": "nana's cauldron", "equipment": None, "alias": False}]


# The list takes in what a recipe brought


async def test_adding_a_recipes_thing_to_the_list_lists_it(mo, people, client, adb) -> None:
    con = await people("con", role="contributor")
    book = await _book(mo)
    pie = await _recipe(con, book, "Waiting Pie", equipment=["pie bird"])
    bird = (await _shown(con, pie))["equipment"][0]["options"][0]["id"]
    assert (await client.get(f"/api/equipment/{bird}")).status_code == 404
    # A moderator adds the name: it is that thing, and everyone's now.
    added = await mo.post("/api/equipment", json={"name": "Pie Bird"})
    assert added.status_code == 201, added.text
    assert added.json() == {"id": bird, "name": "Pie Bird"}
    shown = (await client.get(f"/api/equipment/{bird}")).json()
    # The recipe that needs it still waits: it isn't counted for a stranger.
    assert (shown["name"], shown["total"]) == ("Pie Bird", 0)
    # And it stays when that recipe goes.
    assert (await con.delete(f"/api/recipes/{pie}")).status_code == 204
    assert (await client.get(f"/api/equipment/{bird}")).status_code == 200
    # Not as any kitchen's, while a recipe lists it.
    other = await _recipe(mo, book, "Trifle", equipment=["trifle bowl"])
    refused = await mo.post("/api/equipment", json={"name": "Trifle bowl", "assumed": True})
    assert refused.status_code == 409 and "1 recipe lists" in refused.json()["detail"]
    assert _needs(await _shown(client, other)) == [(None, ["Trifle bowl"])]


# A recipe's needs as one cell, as bulk entry has them


@pytest.mark.parametrize(
    ("cell", "typed", "nothing_special"),
    [
        ("", [], False),
        ("   ", [], False),
        ("none", [], True),
        (" None ", [], True),
        ("Nothing special", [], True),
        ("stand mixer", ["stand mixer"], False),
        (
            "stand mixer or hand mixer, 9-inch springform pan; wok\n kitchen  scale ,",
            ["stand mixer or hand mixer", "9-inch springform pan", "wok", "kitchen scale"],
            False,
        ),
    ],
)
def test_a_cell_is_its_needs_or_none_or_nothing_said(cell, typed, nothing_special) -> None:
    assert needs.from_cell(cell) == (typed, nothing_special)


def test_none_beside_a_need_is_neither() -> None:
    with pytest.raises(needs.Refused) as refused:
        needs.from_cell("none, wok")
    assert "needs nothing special" in str(refused.value)


async def test_a_rows_cell_saves_and_comes_back_as_typed(mo, client, adb) -> None:
    book = await _book(mo)
    cake = await _recipe(
        mo, book, "Sponge", equipment_cell="stand mixer or hand mixer, 9-inch springform pan"
    )
    toast = await _recipe(mo, book, "Toast", equipment_cell="none")
    plain = await _recipe(mo, book, "Plain", equipment_cell="")
    assert _needs(await _shown(client, cake)) == [
        (None, ["Stand mixer", "Hand mixer"]),
        ("9-inch", ["Springform pan"]),
    ]
    states = {
        title: (await _shown(client, recipe))["equipment_checked"]
        for title, recipe in (("Sponge", cake), ("Toast", toast), ("Plain", plain))
    }
    assert states == {"Sponge": True, "Toast": True, "Plain": False}
    # Each row's cell, for entering a whole book.
    lines = (await client.get(f"/api/sources/{book}/recipe-lines")).json()
    cells = {row["id"]: row["equipment_cell"] for row in lines}
    assert cells == {
        cake: "Stand mixer or Hand mixer, 9-inch Springform pan",
        toast: "none",
        plain: "",
    }
    # Sent back as it came, nothing is written again.
    before = await adb.scalar(text("SELECT max(id) FROM revisions"))
    for recipe, title in ((cake, "Sponge"), (toast, "Toast"), (plain, "Plain")):
        again = await _body(mo, book, title, equipment_cell=cells[recipe])
        assert (await mo.put(f"/api/recipes/{recipe}", json=again)).status_code == 200
    written = await adb.scalar(
        text(
            "SELECT count(*) FROM revisions WHERE id > :b AND (table_name LIKE '%equipment%'"
            " OR changes ? 'equipment_checked')"
        ),
        {"b": before},
    )
    assert written == 0
    # A cell and a list are two ways to say one thing: not both.
    both = await _body(mo, book, "Sponge", equipment_cell="wok", equipment=["wok"])
    refused = await mo.put(f"/api/recipes/{cake}", json=both)
    assert refused.status_code == 422 and "not both" in refused.json()["detail"]
    # What a cell holds is refused as a box's is.
    bowl = await _body(mo, book, "Sponge", equipment_cell="wok, mixing bowl")
    refused = await mo.put(f"/api/recipes/{cake}", json=bowl)
    assert refused.status_code == 422 and "expected in any kitchen" in refused.json()["detail"]
