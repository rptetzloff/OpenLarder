"""Canonical ingredients: the matching key, matching lines, and reading them back."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in, make_admins
from openlarder.ingredients import match_key

E = uuid.uuid4()


# The key


@pytest.mark.parametrize(
    "a, b",
    [
        ("Cinnamon Sticks", "cinnamon stick"),
        ("Long-Grain Rice", "Long Grain Rice"),
        ("Berries", "berry"),
        ("Tomatoes", "Tomato"),
        ("Black Peppercorns", "Black Peppercorn"),
        ("Salt & Pepper", "salt and pepper"),
        ("St. Germain", "St Germain"),
        ("Peas", "pea"),
    ],
)
def test_variants_share_a_key(a, b) -> None:
    assert match_key(a) == match_key(b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("Rosé", "Rose"),  # the wine and the flower
        ("Fresh Ginger", "Ginger"),
        ("Grass", "Gras"),
        ("Pineapple (Can)", "Pineapple"),
    ],
)
def test_different_ingredients_keep_different_keys(a, b) -> None:
    assert match_key(a) != match_key(b)


def test_a_name_of_only_punctuation_has_no_key() -> None:
    assert match_key("—") == ""


@pytest.mark.parametrize(
    "name, key",
    [("Swiss Chard", "swiss chard"), ("Sea Bass", "sea bass"), ("Blackberries", "blackberri")],
)
def test_the_key_spelled_out(name, key) -> None:
    assert match_key(name) == key


# Matching, through the recipe routes


@pytest.fixture
async def work(adb):
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
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


async def _ingredients(adb):
    return (await adb.scalars(text("SELECT name FROM ingredients ORDER BY name"))).all()


async def test_each_option_is_matched_to_an_ingredient(admin, work, adb) -> None:
    await _add(admin, work, "Cake", "1", ["Grapeseed Oil or Olive Oil", "Egg"])
    assert await _ingredients(adb) == ["Egg", "Grapeseed Oil", "Olive Oil"]
    unmatched = await adb.scalar(
        text("SELECT count(*) FROM ingredient_options WHERE ingredient_id IS NULL")
    )
    assert unmatched == 0


async def test_variants_match_one_ingredient_named_as_the_book_mostly_does(admin, work, adb):
    await _add(admin, work, "A", "1", ["Cinnamon Sticks"])
    await _add(admin, work, "B", "2", ["Cinnamon Stick"])
    await _add(admin, work, "C", "3", ["cinnamon stick"])
    assert await _ingredients(adb) == ["Cinnamon Sticks"]
    distinct = await adb.scalar(
        text("SELECT count(DISTINCT ingredient_id) FROM ingredient_options")
    )
    assert distinct == 1


async def test_a_new_ingredient_takes_the_most_used_spelling(admin, work, adb) -> None:
    """Matched together, as an import or the Admin catch-up does a whole book."""
    for title, page, line in [("A", "1", "Sea Scallops"), ("B", "2", "Sea Scallop")]:
        await _add(admin, work, title, page, [line])
    await adb.execute(text("UPDATE ingredient_options SET ingredient_id = NULL"))
    await adb.execute(text("DELETE FROM ingredients"))
    await _add(admin, work, "C", "3", ["Sea Scallops"])
    assert await _ingredients(adb) == ["Sea Scallops"]


async def test_references_and_components_are_not_ingredients(admin, work, adb) -> None:
    await _add(admin, work, "Basic Cauli-Rice", "269", ["Cauliflower"])
    await _add(
        admin, work, "Curry", "101", ["Basic Cauli-Rice (p. 269)", "Filling (p. 999)", "Chicken"]
    )
    assert await _ingredients(adb) == ["Cauliflower", "Chicken"]


async def test_a_name_with_no_letters_is_left_unmatched(admin, work, adb) -> None:
    await _add(admin, work, "Cake", "1", ["—", "Egg"])
    assert await _ingredients(adb) == ["Egg"]


async def test_an_ingredient_is_shared_across_books(admin, work, adb) -> None:
    other = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Other') RETURNING id"))
    edition = uuid.uuid4()
    await adb.execute(
        text("INSERT INTO editions (id, source_id) VALUES (:id, :w)"), {"id": edition, "w": other}
    )
    await _add(admin, work, "Cake", "1", ["Butter"])
    response = await admin.post(
        f"/api/sources/{other}/recipes",
        json={
            "title": "Toast",
            "editions": [{"edition_id": str(edition)}],
            "ingredients": ["butter"],
        },
    )
    assert response.status_code == 201
    assert await _ingredients(adb) == ["Butter"]


async def test_the_recipe_page_links_each_ingredient(admin, work, adb) -> None:
    recipe = await _add(admin, work, "Cake", "1", ["Egg"])
    egg = await adb.scalar(text("SELECT id FROM ingredients"))
    option = (await admin.get(f"/api/recipes/{recipe}")).json()["lines"][0]["options"][0]
    assert option["ingredient"] == {"id": str(egg), "name": "Egg"}


async def test_an_edit_keeps_the_same_ingredient(admin, work, adb) -> None:
    recipe = await _add(admin, work, "Cake", "1", ["Eggs"])
    egg = await adb.scalar(text("SELECT id FROM ingredients"))
    response = await admin.put(
        f"/api/recipes/{recipe}",
        json={
            "title": "Cake",
            "editions": [{"edition_id": str(E), "page": "1"}],
            "ingredients": ["Egg"],
        },
    )
    assert response.json()["lines"][0]["options"][0]["ingredient"]["id"] == str(egg)
    assert await _ingredients(adb) == ["Eggs"]


# Reading


async def test_the_list_puts_the_most_used_first(admin, work, client) -> None:
    await _add(admin, work, "A", "1", ["Egg", "Butter"])
    await _add(admin, work, "B", "2", ["Egg"])
    listed = (await client.get("/api/ingredients")).json()
    assert [(i["name"], i["recipes"]) for i in listed["ingredients"]] == [("Egg", 2), ("Butter", 1)]
    assert listed["total"] == 2


async def test_the_list_narrows_by_name(admin, work, client) -> None:
    await _add(admin, work, "A", "1", ["Olive Oil", "Grapeseed Oil", "Egg", "100% Rye Flour"])
    names = lambda r: [i["name"] for i in r.json()["ingredients"]]  # noqa: E731
    assert sorted(names(await client.get("/api/ingredients", params={"q": " oil "}))) == [
        "Grapeseed Oil",
        "Olive Oil",
    ]
    # Wildcards are typed characters, not patterns.
    assert names(await client.get("/api/ingredients", params={"q": "%"})) == ["100% Rye Flour"]
    assert names(await client.get("/api/ingredients", params={"q": "_"})) == []


async def test_the_list_says_what_each_comes_under_and_its_other_names(
    admin, work, adb, client
) -> None:
    await _add(admin, work, "Tea", "1", ["Ginger", "Fresh Ginger", "Apple"])
    ginger, fresh = await _id(adb, "Ginger"), await _id(adb, "Fresh Ginger")
    assert (await _parent(admin, fresh, ginger)).status_code == 200
    await _regional(adb, fresh, "Root Ginger", "UK")
    await _regional(adb, fresh, "Green Ginger", None)
    listed = {i["name"]: i for i in (await client.get("/api/ingredients")).json()["ingredients"]}
    assert listed["Fresh Ginger"]["parent"] == {"id": str(ginger), "name": "Ginger"}
    assert listed["Fresh Ginger"]["aliases"] == ["Green Ginger", "Root Ginger (UK)"]
    assert listed["Ginger"]["parent"] is None and listed["Ginger"]["aliases"] == []
    top = (await client.get("/api/ingredients", params={"top": "true", "sort": "name"})).json()
    assert [i["name"] for i in top["ingredients"]] == ["Apple", "Ginger"]
    assert top["total"] == 2


async def test_an_ingredient_lists_its_recipes_with_book_and_page(admin, work, client) -> None:
    cake = await _add(admin, work, "Rhubarb Cake", "112", ["Rhubarb", "Sugar"])
    await _add(admin, work, "Apple Pie", "90", ["Sugar"])
    sugar = next(
        i
        for i in (await client.get("/api/ingredients")).json()["ingredients"]
        if i["name"] == "Sugar"
    )
    shown = (await client.get(f"/api/ingredients/{sugar['id']}")).json()
    assert shown["name"] == "Sugar"
    assert shown["total"] == 2
    assert [(r["title"], r["source_title"], r["pages"]) for r in shown["recipes"]] == [
        ("Apple Pie", "Pink Cake", ["90"]),
        ("Rhubarb Cake", "Pink Cake", ["112"]),
    ]
    assert cake in [r["id"] for r in shown["recipes"]]


async def test_a_recipe_using_an_ingredient_twice_is_listed_once(admin, work, client) -> None:
    await _add(admin, work, "Cake", "1", ["Butter or Margarine", "Margarine"])
    listed = (await client.get("/api/ingredients", params={"q": "margarine"})).json()
    assert listed["ingredients"][0]["recipes"] == 1


async def test_an_unknown_ingredient_is_a_404(client) -> None:
    assert (await client.get(f"/api/ingredients/{uuid.uuid4()}")).status_code == 404


# Fixing the list


async def _id(adb, name):
    return await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": name})


async def _aliases(adb):
    rows = await adb.execute(
        text(
            "SELECT i.name, a.name FROM ingredient_aliases a"
            " JOIN ingredients i ON i.id = a.ingredient_id ORDER BY 1, 2"
        )
    )
    return [tuple(r) for r in rows]


async def _regional(adb, ingredient_id, name, region):
    await adb.execute(
        text(
            "INSERT INTO ingredient_aliases (ingredient_id, name, match_key, region)"
            " VALUES (:i, :n, :k, :r)"
        ),
        {"i": ingredient_id, "n": name, "k": match_key(name), "r": region},
    )


async def test_a_rename_keeps_the_old_name_matching(admin, work, adb) -> None:
    recipe = await _add(admin, work, "Salsa", "1", ["Corriander"])
    old = await _id(adb, "Corriander")
    response = await admin.patch(f"/api/ingredients/{old}", json={"name": "  Coriander "})
    assert response.json() == {"id": str(old), "name": "Coriander"}
    assert await _aliases(adb) == [("Coriander", "Corriander")]
    shown = (await admin.get(f"/api/recipes/{recipe}")).json()["lines"][0]["options"][0]
    assert shown["ingredient"] == {"id": str(old), "name": "Coriander"}
    # The book's spelling, and the new one, both still find it.
    await _add(admin, work, "Curry", "2", ["Corrianders", "coriander"])
    assert await _ingredients(adb) == ["Coriander"]


async def test_a_rename_that_keeps_the_key_adds_no_alias(admin, work, adb) -> None:
    await _add(admin, work, "Salsa", "1", ["green onions"])
    onion = await _id(adb, "green onions")
    await admin.patch(f"/api/ingredients/{onion}", json={"name": "Green Onion"})
    assert await _ingredients(adb) == ["Green Onion"]
    assert await _aliases(adb) == []


async def test_renaming_back_takes_the_alias_back(admin, work, adb) -> None:
    await _add(admin, work, "Salsa", "1", ["Corriander"])
    i = await _id(adb, "Corriander")
    await admin.patch(f"/api/ingredients/{i}", json={"name": "Coriander"})
    await admin.patch(f"/api/ingredients/{i}", json={"name": "Corriander"})
    assert await _aliases(adb) == [("Corriander", "Coriander")]


async def test_a_rename_onto_another_ingredient_offers_it(admin, work, adb) -> None:
    await _add(admin, work, "Salsa", "1", ["Cilantro", "Coriander Leaf", "Lime"])
    cilantro, leaf, lime = [await _id(adb, n) for n in ("Cilantro", "Coriander Leaf", "Lime")]
    await admin.post(f"/api/ingredients/{leaf}/merge", json={"into": str(cilantro)})
    for name in ("cilantro", "coriander-leaf"):  # its name, then another name for it
        response = await admin.patch(f"/api/ingredients/{lime}", json={"name": name})
        assert response.status_code == 409
        assert response.json()["detail"]["ingredient"] == {"id": str(cilantro), "name": "Cilantro"}
    assert await _ingredients(adb) == ["Cilantro", "Lime"]


@pytest.mark.parametrize("name", ["", "—"])
async def test_a_name_needs_a_letter(admin, work, adb, name) -> None:
    await _add(admin, work, "Salsa", "1", ["Lime"])
    response = await admin.patch(f"/api/ingredients/{await _id(adb, 'Lime')}", json={"name": name})
    assert response.status_code == 422
    assert await _ingredients(adb) == ["Lime"]


async def test_merging_moves_everything_and_keeps_the_name(admin, work, adb, client) -> None:
    soup = await _add(admin, work, "Soup", "1", ["Ham Stock or Chicken Stock"])
    stew = await _add(admin, work, "Stew", "2", ["Chicken Broth", "Ham"])
    stock, broth = await _id(adb, "Chicken Stock"), await _id(adb, "Chicken Broth")
    response = await admin.post(f"/api/ingredients/{broth}/merge", json={"into": str(stock)})
    assert response.json() == {"id": str(stock), "name": "Chicken Stock"}
    assert (await client.get(f"/api/ingredients/{broth}")).status_code == 404
    shown = (await client.get(f"/api/ingredients/{stock}")).json()
    assert [r["id"] for r in shown["recipes"]] == [soup, stew]
    assert [a["name"] for a in shown["aliases"]] == ["Chicken Broth"]
    # Found by its other name, and lines written that way match it.
    listed = (await client.get("/api/ingredients", params={"q": "broth"})).json()
    assert [i["name"] for i in listed["ingredients"]] == ["Chicken Stock"]
    await _add(admin, work, "Rice", "3", ["chicken broth"])
    assert await _ingredients(adb) == ["Chicken Stock", "Ham", "Ham Stock"]


async def test_merging_carries_its_aliases(admin, work, adb, client) -> None:
    await _add(admin, work, "Salsa", "1", ["Cilantro", "Coriander Leaf", "chinese parsley"])
    cilantro, leaf, parsley = [
        await _id(adb, n) for n in ("Cilantro", "Coriander Leaf", "chinese parsley")
    ]
    await admin.post(f"/api/ingredients/{parsley}/merge", json={"into": str(leaf)})
    await admin.post(f"/api/ingredients/{leaf}/merge", json={"into": str(cilantro)})
    shown = (await client.get(f"/api/ingredients/{cilantro}")).json()
    assert [a["name"] for a in shown["aliases"]] == ["chinese parsley", "Coriander Leaf"]


async def test_a_regional_alias_matches_no_lines(admin, work, adb) -> None:
    await _add(admin, work, "Salad", "1", ["Green Onion"])
    await _regional(adb, await _id(adb, "Green Onion"), "Spring Onion", "UK")
    await _add(admin, work, "Stir-Fry", "2", ["Spring Onions"])
    assert await _ingredients(adb) == ["Green Onion", "Spring Onions"]


async def test_merging_moves_swaps_and_drops_what_no_longer_makes_sense(admin, work, adb):
    await _add(admin, work, "Cake", "1", ["Butter", "Margarine", "Oil", "Lard"])
    butter, marg, oil, lard = [await _id(adb, n) for n in ("Butter", "Margarine", "Oil", "Lard")]
    swap = "INSERT INTO substitutions (from_ingredient_id, to_ingredient_id) VALUES (:f, :t)"
    pairs = [
        (marg, butter),
        (butter, marg),
        (marg, oil),
        (butter, oil),
        (lard, marg),
        (lard, butter),
        (marg, lard),
    ]
    for f, t in pairs:
        await adb.execute(text(swap), {"f": f, "t": t})
    response = await admin.post(f"/api/ingredients/{marg}/merge", json={"into": str(butter)})
    assert response.status_code == 200
    rows = await adb.execute(
        text(
            "SELECT f.name, t.name FROM substitutions s"
            " JOIN ingredients f ON f.id = s.from_ingredient_id"
            " JOIN ingredients t ON t.id = s.to_ingredient_id ORDER BY 1, 2"
        )
    )
    # Margarine for Butter, either way, would be Butter for Butter;
    # Margarine -> Oil is Butter -> Oil, and Lard -> Margarine is Lard ->
    # Butter, which there are already.
    assert [tuple(r) for r in rows] == [("Butter", "Lard"), ("Butter", "Oil"), ("Lard", "Butter")]


async def test_merging_hands_over_the_family(admin, work, adb) -> None:
    await _add(admin, work, "Plate", "1", ["Cheese", "Cheddar", "Aged Cheddar", "Old Cheddar"])
    cheese, cheddar, aged, old = [
        await _id(adb, n) for n in ("Cheese", "Cheddar", "Aged Cheddar", "Old Cheddar")
    ]
    parent = "UPDATE ingredients SET parent_id = :p WHERE id = :i"
    await adb.execute(text(parent), {"p": cheese, "i": cheddar})
    for i in (aged, old):
        await adb.execute(text(parent), {"p": cheddar, "i": i})
    # Old Cheddar takes Cheddar's place under Cheese; Aged Cheddar moves under it.
    await admin.post(f"/api/ingredients/{cheddar}/merge", json={"into": str(old)})
    rows = await adb.execute(
        text(
            "SELECT c.name, p.name FROM ingredients c"
            " LEFT JOIN ingredients p ON p.id = c.parent_id ORDER BY 1"
        )
    )
    assert [tuple(r) for r in rows] == [
        ("Aged Cheddar", "Old Cheddar"),
        ("Cheese", None),
        ("Old Cheddar", "Cheese"),
    ]


@pytest.mark.parametrize("loop", [False, True])
async def test_merging_a_parent_into_its_child_leaves_no_loop(admin, work, adb, loop) -> None:
    await _add(admin, work, "Plate", "1", ["Cheese", "Cheddar"])
    cheese, cheddar = await _id(adb, "Cheese"), await _id(adb, "Cheddar")
    parent = "UPDATE ingredients SET parent_id = :p WHERE id = :i"
    await adb.execute(text(parent), {"p": cheese, "i": cheddar})
    if loop:  # Not prevented, so not assumed away.
        await adb.execute(text(parent), {"p": cheddar, "i": cheese})
    await admin.post(f"/api/ingredients/{cheese}/merge", json={"into": str(cheddar)})
    assert await adb.scalar(text("SELECT parent_id FROM ingredients")) is None


async def test_an_ingredient_is_not_merged_into_itself_or_nothing(admin, work, adb) -> None:
    await _add(admin, work, "Salsa", "1", ["Lime"])
    lime = await _id(adb, "Lime")
    itself = await admin.post(f"/api/ingredients/{lime}/merge", json={"into": str(lime)})
    assert itself.status_code == 422
    nothing = await admin.post(f"/api/ingredients/{lime}/merge", json={"into": str(uuid.uuid4())})
    assert nothing.status_code == 404
    assert await _ingredients(adb) == ["Lime"]


async def test_only_an_unused_ingredient_is_deleted(admin, work, adb) -> None:
    recipe = await _add(admin, work, "Soup", "1", ["Ham or Chicken Stock"])
    ham = await _id(adb, "Ham")
    assert (await admin.delete(f"/api/ingredients/{ham}")).status_code == 409
    # The line is what was wrong; fixed, Ham is used by nothing.
    await admin.put(
        f"/api/recipes/{recipe}",
        json={
            "title": "Soup",
            "editions": [{"edition_id": str(E), "page": "1"}],
            "ingredients": ["Ham Stock or Chicken Stock"],
        },
    )
    assert (await admin.delete(f"/api/ingredients/{ham}")).status_code == 204
    assert await _ingredients(adb) == ["Chicken Stock", "Ham Stock"]


async def test_an_ingredient_with_a_swap_or_a_child_is_in_use(admin, work, adb) -> None:
    await _add(admin, work, "Cake", "1", ["Butter", "Cheese", "Cheddar"])
    butter, cheese, cheddar = [await _id(adb, n) for n in ("Butter", "Cheese", "Cheddar")]
    await adb.execute(text("DELETE FROM recipes"))
    await adb.execute(
        text("INSERT INTO substitutions (from_ingredient_id, to_ingredient_id) VALUES (:f, :t)"),
        {"f": cheddar, "t": butter},
    )
    await adb.execute(
        text("UPDATE ingredients SET parent_id = :p WHERE id = :i"), {"p": cheese, "i": cheddar}
    )
    for i in (butter, cheese, cheddar):
        assert (await admin.delete(f"/api/ingredients/{i}")).status_code == 409


async def test_deleting_an_alias_stops_it_matching(admin, work, adb, client) -> None:
    await _add(admin, work, "Salsa", "1", ["Cilantro", "Coriander"])
    cilantro, coriander = await _id(adb, "Cilantro"), await _id(adb, "Coriander")
    await admin.post(f"/api/ingredients/{coriander}/merge", json={"into": str(cilantro)})
    alias = (await client.get(f"/api/ingredients/{cilantro}")).json()["aliases"][0]["id"]
    other = await admin.delete(f"/api/ingredients/{uuid.uuid4()}/aliases/{alias}")
    assert other.status_code == 404
    response = await admin.delete(f"/api/ingredients/{cilantro}/aliases/{alias}")
    assert response.status_code == 204
    # Lines already matched stay; a new one is an ingredient of its own.
    assert len((await client.get(f"/api/ingredients/{cilantro}")).json()["recipes"]) == 1
    await _add(admin, work, "Curry", "2", ["Coriander"])
    assert await _ingredients(adb) == ["Cilantro", "Coriander"]


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("PATCH", "", {"name": "Lemon"}),
        ("POST", "/merge", {"into": str(uuid.uuid4())}),
        ("DELETE", "", None),
    ],
)
async def test_only_admins_fix_ingredients(admin, work, adb, method, path, body) -> None:
    await _add(admin, work, "Salsa", "1", ["Lime"])
    await adb.execute(text("UPDATE users SET role = 'user'"))
    lime = await _id(adb, "Lime")
    response = await admin.request(method, f"/api/ingredients/{lime}{path}", json=body)
    assert response.status_code == 403
    assert await _ingredients(adb) == ["Lime"]


# Broader and narrower


async def _parent(client, child, parent):
    body = {"parent": str(parent) if parent else None}
    return await client.put(f"/api/ingredients/{child}/parent", json=body)


async def test_an_ingredient_goes_under_another(admin, work, adb, client) -> None:
    await _add(admin, work, "Stir-Fry", "1", ["Fresh Ginger", "Garlic"])
    await _add(admin, work, "Cake", "2", ["Ground Ginger", "Fresh Ginger"])
    await _add(admin, work, "Tea", "3", ["Ginger"])
    ginger, fresh, ground = [await _id(adb, n) for n in ("Ginger", "Fresh Ginger", "Ground Ginger")]
    for child in (ground, fresh):
        response = await _parent(admin, child, ginger)
        assert response.status_code == 200, response.text
    shown = (await client.get(f"/api/ingredients/{ginger}")).json()
    assert shown["parent"] is None
    assert [c["name"] for c in shown["children"]] == ["Fresh Ginger", "Ground Ginger"]
    # Its own recipe, and the two of its children's, each once.
    assert (shown["total"], shown["family_total"]) == (1, 3)
    child = (await client.get(f"/api/ingredients/{fresh}")).json()
    assert child["parent"] == {"id": str(ginger), "name": "Ginger"}
    assert child["children"] == []
    assert child["family_total"] == child["total"] == 2


async def test_an_ingredient_can_come_out_from_under(admin, work, adb, client) -> None:
    await _add(admin, work, "Tea", "1", ["Ginger", "Fresh Ginger"])
    ginger, fresh = await _id(adb, "Ginger"), await _id(adb, "Fresh Ginger")
    await _parent(admin, fresh, ginger)
    assert (await _parent(admin, fresh, None)).status_code == 200
    assert (await client.get(f"/api/ingredients/{fresh}")).json()["parent"] is None


async def test_no_loops(admin, work, adb) -> None:
    await _add(admin, work, "Plate", "1", ["Cheese", "Cheddar", "Aged Cheddar"])
    cheese, cheddar, aged = [await _id(adb, n) for n in ("Cheese", "Cheddar", "Aged Cheddar")]
    await _parent(admin, cheddar, cheese)
    await _parent(admin, aged, cheddar)
    for child, parent in [(cheese, cheese), (cheese, cheddar), (cheese, aged)]:
        response = await _parent(admin, child, parent)
        assert response.status_code == 422
    assert await adb.scalar(text("SELECT parent_id FROM ingredients WHERE name = 'Cheese'")) is None
    # Moving a branch elsewhere is fine.
    assert (await _parent(admin, aged, cheese)).status_code == 200


async def test_an_unknown_parent_is_a_404(admin, work, adb) -> None:
    await _add(admin, work, "Tea", "1", ["Ginger"])
    response = await _parent(admin, await _id(adb, "Ginger"), uuid.uuid4())
    assert response.status_code == 404


async def test_only_admins_set_a_parent(admin, work, adb) -> None:
    await _add(admin, work, "Tea", "1", ["Ginger", "Fresh Ginger"])
    await adb.execute(text("UPDATE users SET role = 'user'"))
    response = await _parent(admin, await _id(adb, "Fresh Ginger"), await _id(adb, "Ginger"))
    assert response.status_code == 403


async def test_an_ingredients_page_lists_whats_under_it_on_request(admin, work, adb, client):
    """Ray's wireframe: counting what's under it, or only this exact one; each
    recipe with the line naming it as written."""
    await _add(admin, work, "Ginger Cake", "1", ["Flour", "Ginger"])
    await _add(admin, work, "Stir-Fry", "2", ["Fresh Ginger, peeled", "Garlic"])
    ginger, fresh = await _id(adb, "Ginger"), await _id(adb, "Fresh Ginger, peeled")
    await _parent(admin, fresh, ginger)
    exact = (await client.get(f"/api/ingredients/{ginger}")).json()
    assert [(r["title"], r["line"]) for r in exact["recipes"]] == [("Ginger Cake", "Ginger")]
    assert (exact["total"], exact["listed_total"], exact["family_total"]) == (1, 1, 2)
    under = (await client.get(f"/api/ingredients/{ginger}", params={"under": "true"})).json()
    assert [(r["title"], r["line"]) for r in under["recipes"]] == [
        ("Ginger Cake", "Ginger"),
        ("Stir-Fry", "Fresh Ginger, peeled"),
    ]
    # The exact count stays exact: it is what decides whether it can be deleted.
    assert (under["total"], under["listed_total"]) == (1, 2)
