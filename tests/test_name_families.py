"""Ingredients that count as another by their names (name_families.py),
and their suggestions in the queue (routers/suggestions.py): which names
a family takes and leaves, what a sweep files, and accepting a family
together. *Ray, 2026-11-17: a list he approves.*"""

import json

import pytest
from sqlalchemy import text

from openlarder import ingredients, name_families

QUEUE = "/api/suggestions"


def _counts_as(*names: str) -> dict[str, str]:
    return {child: above for child, (above, _) in name_families.found(names).items()}


def test_a_family_takes_the_names_that_end_with_its_head() -> None:
    found = name_families.found(
        ["Cheese", "Goat Cheese", "Cheddar Cheese", "Sharp Cheddar Cheese", "Cheesecake", "Lettuce"]
    )
    # Each as the nearest of its family that its name ends with, and the
    # family's head beside it. The head isn't one of its own family, and a
    # word that only begins with it isn't either.
    assert found == {
        "Goat Cheese": ("Cheese", "Cheese"),
        "Cheddar Cheese": ("Cheese", "Cheese"),
        "Sharp Cheddar Cheese": ("Cheddar Cheese", "Cheese"),
    }
    # Whole words: a pineapple is not an apple, nor a crabapple one.
    assert _counts_as("Apple", "Pineapple", "Crabapple", "Gala Apple") == {"Gala Apple": "Apple"}
    # In any case, and answered as each is written.
    assert _counts_as("CHEESE", "full-fat cream cheese", "Cream Cheese") == {
        "full-fat cream cheese": "Cream Cheese",
        "Cream Cheese": "CHEESE",
    }
    # A family whose head isn't an ingredient here has no members.
    assert _counts_as("Goat Cheese", "Blue Cheese") == {}


def test_only_the_families_listed() -> None:
    """What was refused, or not looked at, suggests nothing: by name alone
    these were most of 4,464, and the wrong ones pass an allergen down."""
    names = [
        "Butter",
        "Almond Butter",
        "Peanut Butter",
        "Milk",
        "Coconut Milk",
        "Oat Milk",
        "Pepper",
        "Dr Pepper",
        "Bell Pepper",
        "Powder",
        "Baking Powder",
        "Flour",
        "Almond Flour",
        "Cream",
        "Ice Cream",
        "Oil",
        "Lavender Essential Oil",
        "Sauce",
        "Fish Sauce",
    ]
    assert _counts_as(*names) == {}
    # A narrower family inside a refused word is one of its own.
    assert _counts_as("Powder", "Chili Powder", "Ancho Chili Powder", "Oil", "Olive Oil") == {
        "Ancho Chili Powder": "Chili Powder"
    }
    assert _counts_as("Flour", "Wheat Flour", "Whole Wheat Flour", "Almond Flour") == {
        "Whole Wheat Flour": "Wheat Flour"
    }
    assert len(name_families.FAMILIES) == 69


@pytest.mark.parametrize(
    ("head", "left", "kept"),
    [
        # Two things, and stand-ins, from every family.
        (
            "Olive Oil",
            ["Anchovy in Olive Oil", "Sun-Dried Tomato in Olive Oil"],
            ["Light Olive Oil"],
        ),
        ("Vinegar", ["Rice Vinegar and Balsamic Vinegar"], ["Rice Vinegar", "Balsamic Vinegar"]),
        (
            "Cheese",
            ["Dairy-Free Cheese", "Lactose-Free Cream Cheese", "Vegan Cheese"],
            ["Vegetarian Cheese"],
        ),
        ("Chile", ["Other Chile", "Pickled Chile", "Ground Chile"], ["Dried Ancho Chile"]),
        (
            "Sugar",
            ["Palm Sugar, Coconut Palm Sugar", "Cinnamon Sugar"],
            ["Coconut Sugar", "Brown Sugar"],
        ),
        # A fruit or a vegetable only as it grows; a herb dried is the herb.
        (
            "Apple",
            ["Dried Apple", "Freeze-Dried Apple", "Sweet Pickled Apple"],
            ["Granny Smith Apple"],
        ),
        ("Oregano", [], ["Dried Oregano", "Ground Oregano"]),
        ("Onion", ["Green Onion", "Spring Onion", "Dried Minced Onion"], ["Pearl Onion"]),
        ("Potato", ["Sweet Potato", "Japanese Sweet Potato"], ["Russet Potato"]),
        ("Lettuce", ["Sea Lettuce"], ["Romaine Lettuce"]),
        # What must never stand in for the head.
        (
            "Salt",
            ["Curing Salt", "Pink Curing Salt", "Pink Salt", "Garlic Salt"],
            ["Pink Himalayan Salt", "Kosher Salt"],
        ),
        ("Yogurt", ["Coconut Yogurt", "Soy Yogurt", "Frozen Yogurt"], ["Greek Yogurt"]),
        (
            "Wine",
            ["Rice Wine", "Shaoxing Wine", "Chinese Cooking Wine"],
            ["Port Wine", "Dry White Wine"],
        ),
        ("Beer", ["Ginger Beer", "Root Beer", "Gluten-Free Beer"], ["Stout Beer"]),
        (
            "Rice",
            ["Cauliflower Rice", "Puffed Rice", "Red Yeast Rice"],
            ["Wild Rice", "Basmati Rice"],
        ),
        ("Mustard", ["Dry Mustard", "Sea Mustard", "Garlic-Free Mustard"], ["Dijon Mustard"]),
    ],
)
def test_what_a_family_leaves_out(head: str, left: list[str], kept: list[str]) -> None:
    found = _counts_as(head, *left, *kept)
    assert sorted(found) == sorted(kept), head
    for name in left:
        assert name_families.left_out(name, head), name
    # Every word that leaves a name out is one a folded name can have.
    assert all(w == w.casefold() and " " not in w for w in name_families.FAMILIES[head])


# In the queue


@pytest.fixture
async def mo(people):
    return await people("mo", role="moderator")


@pytest.fixture
async def ad(people):
    return await people("ad", admin=True)


async def _add(adb, *names: str) -> dict[str, str]:
    """Ingredients nothing uses yet, which anyone can see."""
    made = {}
    for name in names:
        made[name] = str(
            await adb.scalar(
                text("INSERT INTO ingredients (name, match_key) VALUES (:n, :k) RETURNING id"),
                {"n": name, "k": ingredients.match_key(name)},
            )
        )
    return made


CHEESES = ("Cheese", "Goat Cheese", "Jack Cheese", "Pepper Jack Cheese", "Dairy-Free Cheese")


async def _open(c) -> list[dict]:
    listed = await c.get(QUEUE, params={"kind": "parent"})
    assert listed.status_code == 200, listed.text
    return listed.json()["suggestions"]


def _said(found: list[dict]) -> list[tuple[str, str]]:
    return sorted((s["a"]["name"], s["b"]["name"]) for s in found)


async def _above(adb) -> dict[str, str | None]:
    rows = await adb.execute(
        text(
            "SELECT c.name, p.name FROM ingredients c LEFT JOIN ingredients p ON p.id = c.parent_id"
        )
    )
    return dict(tuple(r) for r in rows)


async def test_an_administrator_files_the_families(mo, ad, people, client, adb) -> None:
    made = await _add(adb, *CHEESES, "Butter", "Almond Butter")
    address = f"{QUEUE}/families"
    # Its button is an administrator's, as the other rules' are.
    assert (await client.post(address)).status_code == 401
    for other in (mo, await people("con", role="contributor")):
        assert (await other.post(address)).status_code == 403
    assert (await ad.post(address)).json() == {"suggested": 3}
    found = await _open(mo)
    assert _said(found) == [
        ("Goat Cheese", "Cheese"),
        ("Jack Cheese", "Cheese"),
        ("Pepper Jack Cheese", "Jack Cheese"),
    ]
    one = next(s for s in found if s["a"]["name"] == "Pepper Jack Cheese")
    assert (one["kind"], one["decision"], one["certainty"]) == ("parent", "a_under_b", "likely")
    assert one["reason"] == "Its name ends with “Jack Cheese”, one of the Cheese family."
    assert (one["model"], one["prompt_version"]) == ("rules", "name-families-v1")
    assert one["family"] == {"id": made["Cheese"], "name": "Cheese", "others": 2}
    assert one["actionable"] is True
    # Again, and nothing is new; nothing counts as anything until accepted.
    assert (await ad.post(address)).json() == {"suggested": 0}
    assert set((await _above(adb)).values()) == {None}


async def test_whats_decided_or_said_already_isnt_suggested(mo, ad, adb) -> None:
    made = await _add(adb, *CHEESES, "Blue Cheese", "Swiss Cheese", "Feta Cheese")
    # One counts as something already: someone has said what.
    await adb.execute(
        text("UPDATE ingredients SET parent_id = :p WHERE id = :i"),
        {"p": made["Jack Cheese"], "i": made["Blue Cheese"]},
    )
    # One pair was suggested by something else and dismissed, another is
    # open from it: neither is filed again.
    for child, status in (("Swiss Cheese", "dismissed"), ("Feta Cheese", "open")):
        await adb.execute(
            text(
                "INSERT INTO suggestions (kind, target, proposal, reason, model, prompt_version,"
                " status, decided_at) VALUES ('parent', CAST(:t AS jsonb), CAST(:p AS jsonb),"
                " 'because', 'wikidata', 'wikidata-names-v1', :s,"
                " CASE WHEN :s = 'open' THEN NULL ELSE now() END)"
            ),
            {
                "t": json.dumps(sorted([made[child], made["Cheese"]])),
                "p": json.dumps(
                    {"a_id": made[child], "b_id": made["Cheese"], "decision": "a_under_b"}
                ),
                "s": status,
            },
        )
    assert (await ad.post(f"{QUEUE}/families")).json() == {"suggested": 3}
    mine = [s for s in await _open(mo) if s["model"] == "rules"]
    assert _said(mine) == [
        ("Goat Cheese", "Cheese"),
        ("Jack Cheese", "Cheese"),
        ("Pepper Jack Cheese", "Jack Cheese"),
    ]
    # Dismissed, it's been decided: not suggested again.
    goat = next(s for s in mine if s["a"]["name"] == "Goat Cheese")
    assert (await mo.post(f"{QUEUE}/{goat['id']}/dismiss")).status_code == 200
    assert (await ad.post(f"{QUEUE}/families")).json() == {"suggested": 0}
    # What something else suggested is one of no family.
    feta = next(s for s in await _open(mo) if s["model"] == "wikidata")
    assert feta["family"] is None
    refused = await mo.post(f"{QUEUE}/{feta['id']}/accept-family")
    assert refused.status_code == 409 and "by itself" in refused.json()["detail"]
    # And only a "counts as" suggestion is one of a family, whatever
    # another kind's proposal says.
    merge = str(
        await adb.scalar(
            text(
                "INSERT INTO suggestions (kind, target, proposal, reason, model, prompt_version)"
                " VALUES ('merge', CAST(:t AS jsonb), CAST(:p AS jsonb), 'because', 'gemma4:12b',"
                " 'merge-v2') RETURNING id"
            ),
            {
                "t": json.dumps(sorted([made["Jack Cheese"], made["Blue Cheese"]])),
                "p": json.dumps(
                    {
                        "a_id": made["Jack Cheese"],
                        "b_id": made["Blue Cheese"],
                        "decision": "same",
                        "keep_name": "a",
                        "family_id": made["Cheese"],
                    }
                ),
            },
        )
    )
    listed = (await mo.get(QUEUE, params={"kind": "merge"})).json()["suggestions"]
    assert [s["family"] for s in listed if s["id"] == merge] == [None]
    assert (await mo.post(f"{QUEUE}/{merge}/accept-family")).status_code == 409


async def test_an_ingredient_only_a_private_recipe_uses_is_never_suggested(
    mo, ad, people, adb
) -> None:
    made = await _add(adb, "Cheese", "Goat Cheese")
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    recipe = await ann.post(
        f"/api/sources/{box}/recipes", json={"title": "Nana's", "ingredients": ["moonbeam cheese"]}
    )
    assert recipe.status_code == 201, recipe.text
    assert (await ad.post(f"{QUEUE}/families")).json() == {"suggested": 1}
    assert await adb.scalar(text("SELECT count(*) FROM suggestions")) == 1
    assert _said(await _open(mo)) == [("Goat Cheese", "Cheese")]
    # One that becomes hers alone after it was filed is out of the queue,
    # out of the family's count, and not accepted with the family.
    await _add(adb, "Blue Cheese")
    assert (await ad.post(f"{QUEUE}/families")).json() == {"suggested": 1}
    used = await ann.post(
        f"/api/sources/{box}/recipes",
        json={"title": "Nana's Other", "ingredients": ["goat cheese"]},
    )
    assert used.status_code == 201, used.text
    [blue] = await _open(mo)
    assert (blue["a"]["name"], blue["family"]["others"]) == ("Blue Cheese", 0)
    done = await mo.post(f"{QUEUE}/{blue['id']}/accept-family")
    assert done.json() == {"done": 1, "skipped": 0}
    above = await _above(adb)
    assert (above["Blue Cheese"], above["Goat Cheese"]) == ("Cheese", None)
    assert (
        await adb.scalar(
            text("SELECT status FROM suggestions WHERE proposal ->> 'a_id' = :i"),
            {"i": made["Goat Cheese"]},
        )
        == "open"
    )


async def test_a_family_is_accepted_together(mo, ad, people, client, adb) -> None:
    made = await _add(adb, *CHEESES, "Blue Cheese", "Onion", "Pearl Onion", "Red Pearl Onion")
    assert (await ad.post(f"{QUEUE}/families")).json() == {"suggested": 6}
    found = await _open(mo)
    goat = next(s for s in found if s["a"]["name"] == "Goat Cheese")
    assert goat["family"]["others"] == 3
    # Since it was suggested, someone has said blue cheese counts as
    # something else: that one is left for a decision of its own.
    await adb.execute(
        text("UPDATE ingredients SET parent_id = :p WHERE id = :i"),
        {"p": made["Goat Cheese"], "i": made["Blue Cheese"]},
    )
    address = f"{QUEUE}/{goat['id']}/accept-family"
    assert (await client.post(address)).status_code == 401
    for other in (await people("ann"), await people("con", role="contributor")):
        assert (await other.post(address)).status_code == 403
    assert set((await _above(adb)).values()) == {None, "Goat Cheese"}

    done = await mo.post(address)
    assert done.status_code == 200, done.text
    assert done.json() == {"done": 3, "skipped": 1}
    # Each counts as the nearest of the family; the other family is as it
    # was, and so is what someone set.
    above = await _above(adb)
    assert above["Goat Cheese"] == above["Jack Cheese"] == "Cheese"
    assert above["Pepper Jack Cheese"] == "Jack Cheese"
    assert above["Blue Cheese"] == "Goat Cheese"
    assert above["Pearl Onion"] is None and above["Red Pearl Onion"] is None
    still = await _open(mo)
    assert _said(still) == [
        ("Blue Cheese", "Cheese"),
        ("Pearl Onion", "Onion"),
        ("Red Pearl Onion", "Pearl Onion"),
    ]
    assert next(s for s in still if s["a"]["name"] == "Blue Cheese")["family"]["others"] == 0
    assert next(s for s in still if s["a"]["name"] == "Pearl Onion")["family"]["others"] == 1
    # Each is the moderator's edit, marked with what suggested it.
    decided = await adb.execute(
        text(
            "SELECT s.status, u.display_name FROM suggestions s JOIN users u ON u.id = s.decided_by"
            " WHERE s.proposal ->> 'family_id' = :f AND s.status <> 'open'"
        ),
        {"f": made["Cheese"]},
    )
    assert sorted(tuple(r) for r in decided) == [("accepted", "mo")] * 3
    history = (await client.get(f"/api/ingredients/{made['Jack Cheese']}/history")).json()
    assert history[0]["by"] == "mo" and history[0]["via"].startswith("suggestion:")
    # And a search for the head now finds a member's recipe.
    again = await mo.post(address)
    assert again.status_code == 409


async def test_a_search_for_the_head_finds_an_accepted_members_recipes(mo, ad, adb, client) -> None:
    await _add(adb, "Cheese")
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": []})).json()[
        "id"
    ]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    made = await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Chèvre Toast",
            "editions": [{"edition_id": edition}],
            "ingredients": ["goat cheese"],
        },
    )
    assert made.status_code == 201, made.text
    cheese = str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Cheese'")))
    before = (await client.get("/api/search", params={"ingredient": cheese})).json()
    assert before["total"] == 0
    assert (await ad.post(f"{QUEUE}/families")).json() == {"suggested": 1}
    [one] = await _open(mo)
    assert (await mo.post(f"{QUEUE}/{one['id']}/accept", json={})).status_code == 200
    after = (await client.get("/api/search", params={"ingredient": cheese})).json()
    assert [r["title"] for r in after["recipes"]] == ["Chèvre Toast"]
