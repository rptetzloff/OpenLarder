"""Equipment in the Suggestions queue (equipment_rules.sweep, routers/
suggestions.py): which recipes get a suggestion, and what accepting and
dismissing one does. The rules themselves are tests/test_equipment_rules.py.
*Ray's equipment spec, 2026-11-15.*"""

import pytest
from sqlalchemy import text

QUEUE = "/api/suggestions"


@pytest.fixture
async def mo(people):
    return await people("mo", role="moderator")


@pytest.fixture
async def ad(people):
    return await people("ad", admin=True)


async def _book(c, adb, title="Plenty") -> tuple[str, str]:
    book = (await c.post("/api/sources/manual", json={"title": title, "authors": []})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    return book, edition


async def _recipe(c, book: tuple[str, str], title: str, **more) -> str:
    body = {"title": title, "editions": [{"edition_id": book[1]}], "ingredients": ["eggs"], **more}
    made = await c.post(f"/api/sources/{book[0]}/recipes", json=body)
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def _open(c, **params) -> list[dict]:
    listed = await c.get(QUEUE, params={"kind": "equipment", **params})
    assert listed.status_code == 200, listed.text
    return listed.json()["suggestions"]


def _said(found: list[dict]) -> list[tuple[str, str]]:
    return sorted((s["recipe"]["title"], s["equipment"]["name"]) for s in found)


async def _needs(c, recipe: str) -> tuple[bool, list[str]]:
    shown = (await c.get(f"/api/recipes/{recipe}")).json()
    return shown["equipment_checked"], [need["text"] for need in shown["equipment"]]


async def test_a_recipe_saved_with_no_equipment_said_gets_a_suggestion(mo, people, adb) -> None:
    book = await _book(mo, adb)
    gelato = await _recipe(mo, book, "Peach Gelato")
    # Someone has said what these need, or that they need nothing special:
    # they've looked, and the rule knows less.
    await _recipe(mo, book, "Lemon Sorbet", equipment=["blender"])
    await _recipe(mo, book, "Ice Cream Sandwiches", nothing_special=True)
    await _recipe(mo, book, "Roast Chicken")
    [found] = await _open(mo)
    assert (found["recipe"]["id"], found["recipe"]["title"]) == (gelato, "Peach Gelato")
    assert found["recipe"]["source_title"] == "Plenty"
    assert (found["equipment"]["name"], found["equipment"]["exists"]) == ("Ice cream maker", True)
    assert found["equipment"]["already"] is False
    assert (found["reason"], found["actionable"]) == ("Its title says “gelato”.", True)
    assert (found["model"], found["prompt_version"]) == ("rules", "equipment-rules-v1")
    # A title changed is read again, and saving it twice suggests it once.
    changed = await mo.put(
        f"/api/recipes/{gelato}",
        json={
            "title": "Peach Gelato Waffles",
            "editions": [{"edition_id": book[1]}],
            "ingredients": ["eggs"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert _said(await _open(mo)) == [
        ("Peach Gelato Waffles", "Ice cream maker"),
        ("Peach Gelato Waffles", "Waffle iron"),
    ]
    # The queue is the moderators'.
    assert (await (await people("ann")).get(QUEUE)).status_code == 403


async def test_only_recipes_anyone_can_see(mo, people, adb) -> None:
    book = await _book(mo, adb)
    con = await people("con", role="contributor")
    waiting = await _recipe(con, book, "Smoked Trout")
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    family = await ann.post(
        f"/api/sources/{box}/recipes", json={"title": "Nana's Waffles", "ingredients": ["eggs"]}
    )
    assert family.status_code == 201, family.text
    # One waiting for review, one in a family's collection: neither. Not
    # filed and then kept from the list: not filed, so no row holds the
    # title of a recipe that isn't everyone's to see. Nor by a sweep of
    # everything.
    filed = text("SELECT count(*) FROM suggestions WHERE kind = 'equipment'")
    assert await _open(mo) == []
    assert await adb.scalar(filed) == 0
    assert (await (await people("ad", admin=True)).post(f"{QUEUE}/equipment")).json() == {
        "suggested": 0
    }
    assert await adb.scalar(filed) == 0
    approved = await mo.post(f"/api/review/recipes/{waiting}", json={"action": "approve"})
    assert approved.status_code == 200, approved.text
    assert _said(await _open(mo)) == [("Smoked Trout", "Smoker")]
    # Sent back since, it's out of the queue for everyone.
    await adb.execute(text("UPDATE recipes SET review = 'returned' WHERE id = :r"), {"r": waiting})
    assert await _open(mo) == []
    listed = (await mo.get(QUEUE)).json()
    assert listed["open_by_kind"].get("equipment", 0) == 0


async def test_accepting_adds_the_need_and_leaves_the_list_open(mo, ad, adb) -> None:
    book = await _book(mo, adb)
    ribs = await _recipe(mo, book, "Smoked and Grilled Ribs")
    assert await _needs(mo, ribs) == (False, [])
    found = {s["equipment"]["name"]: s for s in await _open(mo)}
    assert sorted(found) == ["Grill", "Smoker"]
    accepted = await mo.post(f"{QUEUE}/{found['Smoker']['id']}/accept", json={})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    # The need is there; nobody has said it's all the recipe needs.
    assert await _needs(mo, ribs) == (False, ["Smoker"])
    # The other goes after it, and that's still not the whole list.
    await mo.post(f"{QUEUE}/{found['Grill']['id']}/accept", json={})
    assert await _needs(mo, ribs) == (False, ["Smoker", "Grill"])
    assert await _open(mo) == []
    # Decided once: not again, and not suggested again.
    again = await mo.post(f"{QUEUE}/{found['Grill']['id']}/accept", json={})
    assert again.status_code == 409
    assert (await ad.post(f"{QUEUE}/equipment")).json() == {"suggested": 0}
    decided = await _open(mo, state="decided")
    assert sorted(s["status"] for s in decided) == ["accepted", "accepted"]
    # It's the moderator's edit, marked with what suggested it.
    via = await adb.scalar(
        text(
            "SELECT count(*) FROM revisions WHERE table_name = 'recipe_equipment'"
            " AND via LIKE 'suggestion:%'"
        )
    )
    assert via == 2


async def test_dismissed_it_isnt_suggested_again(mo, ad, adb) -> None:
    book = await _book(mo, adb)
    cheese = await _recipe(mo, book, "Grilled Cheese")
    [found] = await _open(mo)
    assert _said([found]) == [("Grilled Cheese", "Grill")]
    dismissed = await mo.post(f"{QUEUE}/{found['id']}/dismiss")
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "dismissed"
    assert await _needs(mo, cheese) == (False, [])
    # Not by a sweep of everything, nor when it's saved again.
    assert (await ad.post(f"{QUEUE}/equipment")).json() == {"suggested": 0}
    saved = await mo.put(
        f"/api/recipes/{cheese}",
        json={
            "title": "Grilled Cheese",
            "editions": [{"edition_id": book[1]}],
            "ingredients": ["eggs", "bread"],
        },
    )
    assert saved.status_code == 200, saved.text
    assert await _open(mo) == []
    # Sweeping is an administrator's.
    assert (await mo.post(f"{QUEUE}/equipment")).status_code == 403


async def test_what_a_recipe_needs_already_isnt_suggested(mo, ad, adb) -> None:
    book = await _book(mo, adb)
    corn = await _recipe(mo, book, "Grilled Corn", equipment=["charcoal grill"])
    trout = await _recipe(mo, book, "Smoked Trout", equipment=["wok"])
    # As a suggestion accepted leaves them: needs listed, the list not said
    # to be whole.
    await adb.execute(
        text("UPDATE recipes SET equipment_checked = false WHERE id IN (:a, :b)"),
        {"a": corn, "b": trout},
    )
    assert (await ad.post(f"{QUEUE}/equipment")).json() == {"suggested": 1}
    # A charcoal grill is a grill; a wok isn't a smoker.
    assert _said(await _open(mo)) == [("Smoked Trout", "Smoker")]
    # Needed by the time it's accepted, there's nothing to add twice.
    [found] = await _open(mo)
    await mo.put(
        f"/api/recipes/{trout}",
        json={
            "title": "Smoked Trout",
            "editions": [{"edition_id": book[1]}],
            "ingredients": ["eggs"],
            "equipment": ["wok", "smoker"],
        },
    )
    [still] = await _open(mo)
    assert still["equipment"]["already"] is True
    assert (await mo.post(f"{QUEUE}/{found['id']}/accept", json={})).status_code == 200
    assert await _needs(mo, trout) == (True, ["Wok", "Smoker"])


async def test_a_books_title_and_tags_suggest_for_what_they_cover(mo, ad, adb) -> None:
    bible = await _book(mo, adb, "The Slow Cooker Bible")
    await _recipe(mo, bible, "Chili")
    await _recipe(mo, bible, "Beef Stew")
    plain = await _book(mo, adb, "Plenty")
    ribs = await _recipe(mo, plain, "Ribs")
    found = await _open(mo)
    assert _said(found) == [("Beef Stew", "Slow cooker"), ("Chili", "Slow cooker")]
    assert {s["reason"] for s in found} == {"Its source's title says “slow cooker”."}
    # A recipe's own tag, and its source's.
    for table, column, target, tag in (
        ("recipe_tags", "recipe_id", ribs, "Smoking"),
        ("source_tags", "source_id", plain[0], "Grilling"),
    ):
        await adb.execute(
            text(f"INSERT INTO {table} ({column}, tag_id) SELECT :t, id FROM tags WHERE name = :n"),
            {"t": target, "n": tag},
        )
    assert (await ad.post(f"{QUEUE}/equipment")).json() == {"suggested": 2}
    tagged = {
        s["equipment"]["name"]: s["reason"] for s in await _open(mo) if s["recipe"]["id"] == ribs
    }
    assert tagged == {
        "Smoker": "It is tagged Smoking.",
        "Grill": "Its source is tagged Grilling.",
    }


async def test_a_thing_marked_as_any_kitchens_cant_be_accepted(mo, ad, adb) -> None:
    book = await _book(mo, adb)
    await _recipe(mo, book, "Buttermilk Waffles")
    [found] = await _open(mo)
    iron = found["equipment"]["id"]
    marked = await mo.put(f"/api/equipment/{iron}/assumed", json={"assumed": True})
    assert marked.status_code == 200, marked.text
    [now] = await _open(mo)
    assert (now["equipment"]["exists"], now["actionable"]) == (False, False)
    refused = await mo.post(f"{QUEUE}/{found['id']}/accept", json={})
    assert refused.status_code == 409 and "any kitchen" in refused.json()["detail"]
    assert (await mo.post(f"{QUEUE}/{found['id']}/dismiss")).status_code == 200
    # And nothing new is suggested of it.
    await _recipe(mo, book, "Cornmeal Waffles")
    assert await _open(mo) == []
