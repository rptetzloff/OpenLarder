"""Equipment (migration 0079, routers/equipment.py): the list a recipe's
needs are recorded from, what counts as what, and what the database
refuses. *Ray's spec, 2026-11-15.*

Nothing on the site records a recipe's needs yet, so the tests that count
recipes write the rows as the recipe form will."""

import re
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from fake_broker import _sign_in, make_admins
from openlarder import equipment, ingredients


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


async def _id(adb, name: str) -> uuid.UUID:
    found = await adb.scalar(text("SELECT id FROM equipment WHERE name = :n"), {"n": name})
    assert found is not None, name
    return found


async def _recipe(c, source: str, title: str) -> str:
    editions = (await c.get(f"/api/sources/{source}")).json()["editions"]
    body = {"title": title, "ingredients": ["Egg"]}
    if editions:
        body["editions"] = [{"edition_id": editions[0]["id"], "page": "1"}]
    made = await c.post(f"/api/sources/{source}/recipes", json=body)
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def _need(adb, recipe: str, position: int, *names: str, detail: str | None = None) -> None:
    """One need of a recipe, met by each of the things named, first choice
    first."""
    need = await adb.scalar(
        text(
            "INSERT INTO recipe_equipment (recipe_id, position, detail)"
            " VALUES (:r, :p, :d) RETURNING id"
        ),
        {"r": uuid.UUID(recipe), "p": position, "d": detail},
    )
    for rank, name in enumerate(names, start=1):
        await adb.execute(
            text(
                "INSERT INTO equipment_options (recipe_equipment_id, recipe_id, rank, equipment_id)"
                " VALUES (:n, :r, :k, :e)"
            ),
            {"n": need, "r": uuid.UUID(recipe), "k": rank, "e": await _id(adb, name)},
        )


async def _listed(c, **params) -> dict[str, dict]:
    response = await c.get("/api/equipment", params=params)
    assert response.status_code == 200, response.text
    return {e["name"]: e for e in response.json()["equipment"]}


# The list to start from


async def test_a_typed_name_finds_each_thing_by_its_key(adb) -> None:
    """The migration made each key with its own copy of the rule. If the
    app's has moved on since, the list's keys need moving with it."""
    rows = await adb.execute(
        text(
            "SELECT name, match_key FROM equipment"
            " UNION ALL SELECT name, match_key FROM equipment_aliases"
        )
    )
    wrong = [(n, k) for n, k in rows if ingredients.match_key(n) != k]
    assert not wrong, wrong


async def test_a_key_means_one_thing(adb) -> None:
    """The database keeps a key to one thing and to one unmarked other
    name, each in its own table. Across the two it is the list's to keep."""
    twice = await adb.execute(
        text(
            "SELECT match_key FROM (SELECT match_key FROM equipment UNION ALL"
            " SELECT match_key FROM equipment_aliases WHERE region IS NULL) keys"
            " GROUP BY match_key HAVING count(*) > 1"
        )
    )
    assert twice.all() == []


async def test_no_name_offers_two_things(adb) -> None:
    """Typed into a recipe, "A or B" is to be one need with two options, so
    a name holding an "or" could never be typed."""
    rows = await adb.scalars(
        text("SELECT name FROM equipment UNION ALL SELECT name FROM equipment_aliases")
    )
    assert [n for n in rows if re.search(r"\bor\b", n, re.I)] == []


async def test_what_ray_decided_is_recorded_is_and_what_any_kitchen_has_isnt(adb) -> None:
    """Ray, 2026-11-15: a blender, a food processor, a stand mixer and a
    Dutch oven are recorded; shaped pans are, and plain ones aren't."""
    assumed = dict((await adb.execute(text("SELECT name, assumed FROM equipment"))).all())
    for name in ("Blender", "Food processor", "Stand mixer", "Dutch oven"):
        assert assumed[name] is False, name
    for name in ("Springform pan", "Bundt pan", "Tart pan"):
        assert assumed[name] is False, name
    for name in ("Knife", "Mixing bowl", "Baking sheet", "Baking dish", "Skillet"):
        assert assumed[name] is True, name


# The list


async def test_the_list_is_what_a_recipe_can_list(client, adb) -> None:
    found = await _listed(client)
    recorded = await adb.scalar(text("SELECT count(*) FROM equipment WHERE NOT assumed"))
    assert len(found) == recorded > 50
    assert "Stand mixer" in found and "Knife" not in found
    assert not [e for e in found.values() if e["assumed"]]
    # Asked for, what any kitchen has is there too, and says so.
    everything = await _listed(client, assumed=True)
    assert len(everything) == await adb.scalar(text("SELECT count(*) FROM equipment"))
    assert everything["Knife"]["assumed"] is True
    assert everything["Stand mixer"]["assumed"] is False


async def test_a_thing_is_found_by_another_name(client) -> None:
    assert list(await _listed(client, q="stick blender")) == ["Immersion blender"]
    found = await _listed(client, q="mixer")
    assert {"Mixer", "Stand mixer", "Hand mixer"} <= set(found)
    # A skillet is any kitchen's: only looked for among everything.
    assert "Skillet" not in await _listed(client, q="frying pan")
    assert list(await _listed(client, q="frying pan", assumed=True)) == ["Skillet"]
    # A % is a character, not anything at all.
    assert await _listed(client, q="%") == {}


async def test_the_list_says_what_each_counts_as_and_is_also_called(client) -> None:
    found = await _listed(client)
    assert [c["name"] for c in found["Multicooker"]["counts_as"]] == [
        "Pressure cooker",
        "Slow cooker",
    ]
    assert "Instant Pot" in found["Multicooker"]["aliases"]
    assert found["Blender"]["counts_as"] == [] and found["Blender"]["aliases"] == []


async def test_a_to_z_is_by_name(admin, client, adb) -> None:
    book = (
        await admin.post("/api/sources/manual", json={"title": "Woks", "authors": ["Ann Author"]})
    ).json()["id"]
    await _need(adb, await _recipe(admin, book, "Fried Rice"), 1, "Wok")
    assert list(await _listed(client))[0] == "Wok"
    names = list(await _listed(client, sort="name"))
    assert names[0] == "Air fryer"
    assert names.index("Blender") < names.index("Dutch oven") < names.index("Wok")


# One thing


async def test_a_thing_counts_as_several_and_they_include_it(client, adb) -> None:
    """Ray, 2026-11-15: a multicooker counts as a pressure cooker and as a
    slow cooker, which is why this is a table and not a parent."""
    shown = (await client.get(f"/api/equipment/{await _id(adb, 'Multicooker')}")).json()
    assert [c["name"] for c in shown["counts_as"]] == ["Pressure cooker", "Slow cooker"]
    assert {a["name"] for a in shown["aliases"]} >= {"Instant Pot"}
    assert shown["assumed"] is False and shown["includes"] == []
    for broader in ("Pressure cooker", "Slow cooker"):
        there = (await client.get(f"/api/equipment/{await _id(adb, broader)}")).json()
        assert [c["name"] for c in there["includes"]] == ["Multicooker"], broader
    mixer = (await client.get(f"/api/equipment/{await _id(adb, 'Mixer')}")).json()
    assert [c["name"] for c in mixer["includes"]] == ["Hand mixer", "Stand mixer"]


async def test_what_any_kitchen_has_has_a_page_that_says_so(client, adb) -> None:
    shown = (await client.get(f"/api/equipment/{await _id(adb, 'Skillet')}")).json()
    assert shown["assumed"] is True and shown["total"] == 0
    assert {a["name"] for a in shown["aliases"]} == {"Frying pan", "Fry pan"}


async def test_nothing_there_is_not_found(client) -> None:
    missing = await client.get(f"/api/equipment/{uuid.uuid4()}")
    assert missing.status_code == 404 and missing.json()["detail"] == "No such equipment."


# Counting the recipes that need a thing


async def test_a_family_is_a_thing_and_all_that_counts_as_it(adb) -> None:
    async def names(*of: str) -> set[str]:
        ids = [await _id(adb, n) for n in of]
        found = await adb.scalars(
            text("SELECT name FROM equipment WHERE id = ANY(:ids)"),
            {"ids": list(await adb.scalars(equipment.family(*ids)))},
        )
        return set(found)

    assert await names("Mixer") == {"Mixer", "Stand mixer", "Hand mixer"}
    # Up is not down: a stand mixer's family is itself.
    assert await names("Stand mixer") == {"Stand mixer"}
    assert await names("Pressure cooker", "Slow cooker") == {
        "Pressure cooker",
        "Slow cooker",
        "Multicooker",
    }


async def test_a_loop_in_what_counts_as_what_still_ends(adb) -> None:
    """Nothing on the site makes one; the database doesn't refuse it."""
    mixer, stand = await _id(adb, "Mixer"), await _id(adb, "Stand mixer")
    await adb.execute(
        text("INSERT INTO equipment_counts_as (equipment_id, counts_as_id) VALUES (:m, :s)"),
        {"m": mixer, "s": stand},
    )
    assert set(await adb.scalars(equipment.family(stand))) >= {mixer, stand}


async def test_a_recipes_needs_are_counted_once_each(admin, client, adb) -> None:
    book = (
        await admin.post("/api/sources/manual", json={"title": "Cakes", "authors": ["Ann Author"]})
    ).json()["id"]
    cake = await _recipe(admin, book, "Sponge")
    torte = await _recipe(admin, book, "Torte")
    await _need(adb, cake, 1, "Stand mixer", "Hand mixer")
    await _need(adb, cake, 2, "Springform pan", detail="9-inch")
    await _need(adb, torte, 1, "Stand mixer")
    await _need(adb, torte, 2, "Stand mixer", "Food processor")

    found = await _listed(client)
    assert found["Stand mixer"]["recipes"] == 2
    assert found["Hand mixer"]["recipes"] == 1
    assert found["Springform pan"]["recipes"] == 1
    assert found["Mixer"]["recipes"] == 0
    # The most needed first, then by name.
    assert list(found)[:4] == ["Stand mixer", "Food processor", "Hand mixer", "Springform pan"]

    mixer = (await client.get(f"/api/equipment/{await _id(adb, 'Mixer')}")).json()
    assert (mixer["total"], mixer["family_total"]) == (0, 2)
    stand = (await client.get(f"/api/equipment/{await _id(adb, 'Stand mixer')}")).json()
    assert (stand["total"], stand["family_total"]) == (2, 2)


async def test_a_private_recipes_needs_are_its_owners_to_count(people, client, adb) -> None:
    """The thing is everyone's (the list is seeded); that someone's private
    recipe needs it is theirs."""
    ann, bob = await people("ann"), await people("bob")
    box = (
        await ann.post("/api/sources/family", json={"title": "Secret Box", "acknowledged": True})
    ).json()["id"]
    stew = await _recipe(ann, box, "Secret Stew")
    await _need(adb, stew, 1, "Tagine")
    tagine = await _id(adb, "Tagine")
    for other in (client, bob):
        assert (await _listed(other))["Tagine"]["recipes"] == 0
        shown = (await other.get(f"/api/equipment/{tagine}")).json()
        assert (shown["total"], shown["family_total"]) == (0, 0)
    assert (await _listed(ann))["Tagine"]["recipes"] == 1
    assert (await ann.get(f"/api/equipment/{tagine}")).json()["total"] == 1


# What the database refuses


async def _refused(adb, statement: str, **params) -> str:
    with pytest.raises(IntegrityError) as refused:
        async with adb.begin_nested():
            await adb.execute(text(statement), params)
    return str(refused.value)


async def test_the_database_refuses_what_makes_no_sense(admin, adb) -> None:
    mixer, stand = await _id(adb, "Mixer"), await _id(adb, "Stand mixer")
    assert "ck_equipment_counts_as_not_itself" in await _refused(
        adb, "INSERT INTO equipment_counts_as VALUES (:m, :m)", m=mixer
    )
    assert "uq_equipment_name" in await _refused(
        adb, "INSERT INTO equipment (name, match_key) VALUES ('STAND MIXER', 'x')"
    )
    assert "uq_equipment_match_key" in await _refused(
        adb, "INSERT INTO equipment (name, match_key) VALUES ('Standing mixer', 'stand mixer')"
    )
    assert "uq_equipment_aliases_match_key" in await _refused(
        adb,
        "INSERT INTO equipment_aliases (equipment_id, name, match_key)"
        " VALUES (:m, 'Stick-blender', 'stick blender')",
        m=mixer,
    )
    # A thing something counts as is merged away, not deleted from under it.
    assert "fk_equipment_counts_as_counts_as_id_equipment" in await _refused(
        adb, "DELETE FROM equipment WHERE id = :m", m=mixer
    )

    book = (
        await admin.post("/api/sources/manual", json={"title": "Cakes", "authors": ["Ann Author"]})
    ).json()["id"]
    cake, torte = await _recipe(admin, book, "Sponge"), await _recipe(admin, book, "Torte")
    await _need(adb, cake, 1, "Stand mixer")
    need = await adb.scalar(
        text("SELECT id FROM recipe_equipment WHERE recipe_id = :r"), {"r": uuid.UUID(cake)}
    )
    option = (
        "INSERT INTO equipment_options (recipe_equipment_id, recipe_id, rank, equipment_id)"
        " VALUES (:n, :r, :k, :e)"
    )
    # An option is of its need's recipe, has a rank from 1 that no other
    # option of the need has, and names a thing the need doesn't already.
    assert "fk_equipment_options_need" in await _refused(
        adb, option, n=need, r=uuid.UUID(torte), k=2, e=mixer
    )
    assert "ck_equipment_options_rank_positive" in await _refused(
        adb, option, n=need, r=uuid.UUID(cake), k=0, e=mixer
    )
    assert "uq_equipment_options_recipe_equipment_id_rank" in await _refused(
        adb, option, n=need, r=uuid.UUID(cake), k=1, e=mixer
    )
    assert "uq_equipment_options_recipe_equipment_id_equipment_id" in await _refused(
        adb, option, n=need, r=uuid.UUID(cake), k=2, e=stand
    )
    assert "uq_recipe_equipment_recipe_id_position" in await _refused(
        adb, "INSERT INTO recipe_equipment (recipe_id, position) VALUES (:r, 1)", r=uuid.UUID(cake)
    )
    assert "ck_recipe_equipment_detail_not_empty" in await _refused(
        adb,
        "INSERT INTO recipe_equipment (recipe_id, position, detail) VALUES (:r, 2, '')",
        r=uuid.UUID(cake),
    )
    # A thing a recipe needs is merged into another, not deleted.
    assert "fk_equipment_options_equipment_id_equipment" in await _refused(
        adb, "DELETE FROM equipment WHERE id = :s", s=stand
    )
    # Its needs go with a recipe.
    await adb.execute(text("DELETE FROM recipes WHERE id = :r"), {"r": uuid.UUID(cake)})
    assert await adb.scalar(text("SELECT count(*) FROM equipment_options")) == 0


async def test_a_recipe_nobody_has_looked_at_is_not_one_that_needs_nothing(admin, adb) -> None:
    """Three states (models/equipment.py). Every recipe starts in the
    first: not recorded yet."""
    book = (
        await admin.post("/api/sources/manual", json={"title": "Cakes", "authors": ["Ann Author"]})
    ).json()["id"]
    cake = await _recipe(admin, book, "Sponge")
    checked = await adb.scalar(
        text("SELECT equipment_checked FROM recipes WHERE id = :r"), {"r": uuid.UUID(cake)}
    )
    assert checked is False


async def test_updated_at_moves_when_a_row_changes(admin, adb) -> None:
    """The sitemap says when each page last changed. now() is fixed within
    a transaction, so each row is backdated and then changed: without its
    trigger the backdating would stay."""
    book = (
        await admin.post("/api/sources/manual", json={"title": "Cakes", "authors": ["Ann Author"]})
    ).json()["id"]
    await _need(adb, await _recipe(admin, book, "Sponge"), 1, "Wok", detail="14-inch")
    changes = {
        "equipment": "shopping_term = 'carbon steel wok'",
        "equipment_aliases": "region = 'UK'",
        "recipe_equipment": "detail = '12-inch'",
        "equipment_options": "rank = 2",
    }
    for table, change in changes.items():
        one = await adb.scalar(text(f"SELECT id FROM {table} LIMIT 1"))
        await adb.execute(text(f"UPDATE {table} SET updated_at = now() - interval '1 day'"))
        await adb.execute(text(f"UPDATE {table} SET {change} WHERE id = :i"), {"i": one})
        moved = await adb.scalar(
            text(f"SELECT updated_at = now() FROM {table} WHERE id = :i"), {"i": one}
        )
        assert moved, table
