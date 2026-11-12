"""Substitutions and diets: adding, removing, and where swaps are shown."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in, make_admins

E = uuid.uuid4()


@pytest.fixture
async def work(adb):
    work = await adb.scalar(
        text("INSERT INTO sources (title) VALUES ('How Can It Be Gluten Free') RETURNING id")
    )
    await adb.execute(
        text("INSERT INTO editions (id, source_id) VALUES (:id, :w)"), {"id": E, "w": work}
    )
    return work


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


async def _add(client, work, title, page, ingredients):
    response = await client.post(
        f"/api/sources/{work}/recipes",
        json={
            "title": title,
            "editions": [{"edition_id": str(E), "page": page}],
            "ingredients": ingredients,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _id(adb, name):
    return str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": name}))


async def _diet(client, name):
    return next(d["id"] for d in (await client.get("/api/diets")).json() if d["name"] == name)


async def _swap(client, instead_of, use, **more):
    return await client.post(
        "/api/substitutions", json={"instead_of": instead_of, "use": use, **more}
    )


# Diets


async def test_the_diets_start_seeded(client, adb) -> None:
    await adb.execute(text("INSERT INTO tags (kind, name) VALUES ('course', 'Teatime')"))
    names = [d["name"] for d in (await client.get("/api/diets")).json()]
    assert names == [
        "AIP",
        "Dairy-Free",
        "Egg-Free",
        "Gluten-Free",
        "Halal",
        "Kosher",
        "Low-FODMAP",
        "Nut-Free",
        "Paleo",
        "Pescetarian",
        "Soy-Free",
        "Vegan",
        "Vegetarian",
    ]


async def test_an_admin_adds_a_diet_once(admin, client) -> None:
    first = (await admin.post("/api/diets", json={"name": "  Nightshade-Free "})).json()
    again = (await admin.post("/api/diets", json={"name": "nightshade-free"})).json()
    assert first == again
    assert first["name"] == "Nightshade-Free"
    assert "Nightshade-Free" in [d["name"] for d in (await client.get("/api/diets")).json()]
    assert (await admin.post("/api/diets", json={"name": "  "})).status_code == 422


# Adding swaps, and where they show


async def test_a_printed_swap_shows_for_the_ingredient_and_its_recipes(
    admin, work, adb, client
) -> None:
    cake = await _add(admin, work, "Cake", "40", ["Butter", "Flour"])
    await _add(admin, work, "Bread", "41", ["Flour"])
    await _add(admin, work, "Frosting", "42", ["Coconut Oil"])
    butter, coconut = await _id(adb, "Butter"), await _id(adb, "Coconut Oil")
    response = await _swap(
        admin,
        {"ingredient_id": butter},
        {"ingredient_id": coconut},
        diet_id=await _diet(client, "Dairy-Free"),
        source_edition_id=str(E),
        source_page=" 12 ",
        note="  Refined,  so it doesn't taste of coconut. ",
    )
    assert response.status_code == 201, response.text
    swap = response.json()
    assert swap["instead_of"] == {"kind": "ingredient", "id": butter, "name": "Butter"}
    assert swap["use"] == {"kind": "ingredient", "id": coconut, "name": "Coconut Oil"}
    assert swap["diet"]["name"] == "Dairy-Free"
    assert swap["source"] == {
        "source_id": str(work),
        "source_title": "How Can It Be Gluten Free",
        "edition_id": str(E),
        "page": "12",
    }
    assert swap["note"] == "Refined, so it doesn't taste of coconut."
    assert (await client.get(f"/api/ingredients/{butter}")).json()["swaps"] == [swap]
    assert (await client.get(f"/api/ingredients/{coconut}")).json()["swaps"] == []
    assert (await client.get(f"/api/recipes/{cake}")).json()["swaps"] == [swap]


async def test_a_recipe_can_stand_in_and_be_stood_in_for(admin, work, adb, client) -> None:
    ours = await _add(admin, work, "Our Flour Blend", "10", ["Rice Flour"])
    theirs = await _add(admin, work, "Their Flour Blend", "11", ["Sorghum Flour"])
    bread = await _add(admin, work, "Bread", "50", ["Our Flour Blend (p. 10)", "Egg"])
    flax = await _add(admin, work, "Flax Egg", "12", ["Flaxseed"])
    blend = await _swap(admin, {"recipe_id": ours}, {"recipe_id": theirs})
    egg = await _swap(
        admin,
        {"ingredient_id": await _id(adb, "Egg")},
        {"recipe_id": flax},
        diet_id=await _diet(client, "Vegan"),
    )
    assert (blend.status_code, egg.status_code) == (201, 201)
    assert egg.json()["source"] is None  # contributed
    # Bread uses the blend (by reference) and egg; the blend lists its own swap.
    on_bread = (await client.get(f"/api/recipes/{bread}")).json()["swaps"]
    assert [(s["instead_of"]["name"], s["use"]["name"]) for s in on_bread] == [
        ("Egg", "Flax Egg"),
        ("Our Flour Blend", "Their Flour Blend"),
    ]
    on_blend = (await client.get(f"/api/recipes/{ours}")).json()["swaps"]
    assert [s["use"]["kind"] for s in on_blend] == ["recipe"]
    assert (await client.get(f"/api/recipes/{theirs}")).json()["swaps"] == []


@pytest.mark.parametrize(
    "case",
    ["both sides", "neither", "itself", "page alone", "unknown diet", "not a diet", "gone"],
)
async def test_a_bad_swap_is_refused(admin, work, adb, case) -> None:
    await _add(admin, work, "Cake", "1", ["Butter", "Ghee"])
    butter, ghee = await _id(adb, "Butter"), await _id(adb, "Ghee")
    recipe = await adb.scalar(text("SELECT id FROM recipes"))
    course = await adb.scalar(
        text("INSERT INTO tags (kind, name) VALUES ('course', 'Teatime') RETURNING id")
    )
    instead_of, use, more = {"ingredient_id": butter}, {"ingredient_id": ghee}, {}
    if case == "both sides":
        instead_of["recipe_id"] = str(recipe)
    elif case == "neither":
        use = {}
    elif case == "itself":
        use = {"ingredient_id": butter}
    elif case == "page alone":
        more = {"source_page": "12"}
    elif case == "unknown diet":
        more = {"diet_id": str(uuid.uuid4())}
    elif case == "not a diet":
        more = {"diet_id": str(course)}
    elif case == "gone":
        use = {"ingredient_id": str(uuid.uuid4())}
    response = await _swap(admin, instead_of, use, **more)
    assert response.status_code == 422, response.text
    assert await adb.scalar(text("SELECT count(*) FROM substitutions")) == 0


async def test_the_same_swap_twice_is_refused_but_another_source_is_not(
    admin, work, adb, client
) -> None:
    await _add(admin, work, "Cake", "1", ["Butter", "Ghee"])
    sides = ({"ingredient_id": await _id(adb, "Butter")}, {"ingredient_id": await _id(adb, "Ghee")})
    assert (await _swap(admin, *sides)).status_code == 201
    assert (await _swap(admin, *sides)).status_code == 409
    printed = await _swap(admin, *sides, source_edition_id=str(E), source_page="3")
    assert printed.status_code == 201
    for_diet = await _swap(admin, *sides, diet_id=await _diet(client, "Dairy-Free"))
    assert for_diet.status_code == 201


async def test_a_swap_is_removed(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", "1", ["Butter", "Ghee"])
    butter = await _id(adb, "Butter")
    swap = (
        await _swap(admin, {"ingredient_id": butter}, {"ingredient_id": await _id(adb, "Ghee")})
    ).json()
    assert (await admin.delete(f"/api/substitutions/{swap['id']}")).status_code == 204
    assert (await client.get(f"/api/ingredients/{butter}")).json()["swaps"] == []
    assert (await admin.delete(f"/api/substitutions/{swap['id']}")).status_code == 404


async def test_only_admins_change_swaps_and_diets(admin, work, adb) -> None:
    await _add(admin, work, "Cake", "1", ["Butter", "Ghee"])
    sides = ({"ingredient_id": await _id(adb, "Butter")}, {"ingredient_id": await _id(adb, "Ghee")})
    swap = (await _swap(admin, *sides)).json()
    await adb.execute(text("UPDATE users SET role = 'user'"))
    assert (await _swap(admin, *sides, source_edition_id=str(E))).status_code == 403
    assert (await admin.delete(f"/api/substitutions/{swap['id']}")).status_code == 403
    assert (await admin.post("/api/diets", json={"name": "Keto"})).status_code == 403


async def test_swaps_are_listed_by_name(admin, work, adb, client) -> None:
    await _add(admin, work, "Cake", "1", ["Butter", "Ghee", "Coconut Oil", "Lard", "Avocado Oil"])
    butter = await _id(adb, "Butter")
    for name in ("Lard", "Ghee", "Avocado Oil", "Coconut Oil"):
        response = await _swap(
            admin, {"ingredient_id": butter}, {"ingredient_id": await _id(adb, name)}
        )
        assert response.status_code == 201
    shown = (await client.get(f"/api/ingredients/{butter}")).json()["swaps"]
    assert [s["use"]["name"] for s in shown] == ["Avocado Oil", "Coconut Oil", "Ghee", "Lard"]
