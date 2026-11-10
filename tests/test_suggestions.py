"""Suggestions, embeddings, and what n8n's role may read and write (0029)."""

import json
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

ROLE_SQL = Path(__file__).resolve().parents[1] / "scripts" / "n8n_role.sql"


async def _ingredient(adb, name):
    return await adb.scalar(
        text("INSERT INTO ingredients (name, match_key) VALUES (:n, :n) RETURNING id"), {"n": name}
    )


def _vector(*leading: float) -> str:
    values = list(leading) + [0.0] * (768 - len(leading))
    return "[" + ",".join(str(v) for v in values) + "]"


async def test_the_nearest_ingredient_is_found_by_its_embedding(adb) -> None:
    onion, scallion, cocoa = [
        await _ingredient(adb, n) for n in ("green onion", "scallion", "cocoa")
    ]
    for ingredient, vector in (
        (onion, _vector(1, 0.1)),
        (scallion, _vector(1, 0.2)),
        (cocoa, _vector(0, 1)),
    ):
        await adb.execute(
            text(
                "INSERT INTO ingredient_embeddings (ingredient_id, model, text_embedded, embedding)"
                " VALUES (:i, 'embeddinggemma', 'x', CAST(:v AS vector))"
            ),
            {"i": ingredient, "v": vector},
        )
    nearest = await adb.scalar(
        text(
            "SELECT b.ingredient_id FROM ingredient_embeddings a, ingredient_embeddings b"
            " WHERE a.ingredient_id = :o AND b.ingredient_id <> a.ingredient_id"
            " ORDER BY a.embedding <=> b.embedding LIMIT 1"
        ),
        {"o": onion},
    )
    assert nearest == scallion


async def test_a_rerun_adds_no_second_open_suggestion(adb) -> None:
    insert = text(
        "INSERT INTO suggestions (kind, target, proposal, model, prompt_version)"
        " VALUES ('merge', CAST(:t AS jsonb), '{}', 'gemma4:12b', 'merge-v1')"
        " ON CONFLICT DO NOTHING RETURNING id"
    )
    target = json.dumps([str(uuid.uuid4()), str(uuid.uuid4())])
    first = await adb.scalar(insert, {"t": target})
    assert first is not None
    assert await adb.scalar(insert, {"t": target}) is None
    # Once decided, it no longer blocks; the workflow's own NOT EXISTS is
    # what keeps a dismissed pair from coming back.
    await adb.execute(
        text("UPDATE suggestions SET status = 'dismissed', decided_at = now() WHERE id = :i"),
        {"i": first},
    )
    assert await adb.scalar(insert, {"t": target}) is not None


async def test_a_decided_suggestion_says_when(adb) -> None:
    with pytest.raises(IntegrityError):
        async with adb.begin_nested():
            await adb.execute(
                text(
                    "INSERT INTO suggestions"
                    " (kind, target, proposal, model, prompt_version, status)"
                    " VALUES ('merge', '[]', '{}', 'm', 'v', 'accepted')"
                )
            )


# The role, made by the script itself.


@pytest.fixture
async def n8n(adb):
    """The script's role under a throwaway name, and a way to act as it."""
    role = f"n8n_test_{uuid.uuid4().hex[:8]}"
    database = await adb.scalar(text("SELECT current_database()"))
    script = (
        ROLE_SQL.read_text(encoding="utf-8")
        .replace(':"role"', f'"{role}"')
        .replace(':"DBNAME"', f'"{database}"')
        .replace(":'password'", "'not-a-real-password'")
    )
    script = re.sub(r"--[^\n]*", "", script)
    for statement in filter(str.strip, script.split(";")):
        await adb.execute(text(statement))

    async def as_role(sql, **params):
        # SET LOCAL would outlast the savepoint; the role goes with the
        # test's rollback, so nothing is dropped after.
        await adb.execute(text(f'SET ROLE "{role}"'))
        try:
            async with adb.begin_nested():
                return await adb.execute(text(sql), params)
        finally:
            await adb.execute(text("RESET ROLE"))

    return as_role


async def test_the_role_reads_the_views_and_not_the_tables(n8n, adb) -> None:
    await _ingredient(adb, "rhubarb")
    assert [r.name for r in await n8n("SELECT name FROM public_ingredients")] == ["rhubarb"]
    for view in ("public_recipes", "public_tags", "public_recipe_tags"):
        await n8n(f"SELECT 1 FROM {view}")
    for table in ("ingredients", "recipe_ingredients", "sources", "users", "recipe_tags"):
        with pytest.raises(DBAPIError, match="permission denied"):
            await n8n(f"SELECT 1 FROM {table}")


async def test_the_role_writes_embeddings_and_adds_suggestions(n8n, adb) -> None:
    rhubarb = await _ingredient(adb, "rhubarb")
    await n8n(
        "INSERT INTO ingredient_embeddings (ingredient_id, model, text_embedded, embedding)"
        " VALUES (:i, 'embeddinggemma', 'rhubarb', CAST(:v AS vector))",
        i=rhubarb,
        v=_vector(1),
    )
    added = await n8n(
        "INSERT INTO suggestions (kind, target, proposal, model, prompt_version)"
        " VALUES ('merge', '[1, 2]', '{}', 'gemma4:12b', 'merge-v1') RETURNING id"
    )
    suggestion = added.scalar()
    # Deciding is the site's.
    for sql in (
        "UPDATE suggestions SET status = 'accepted', decided_at = now()",
        "DELETE FROM suggestions",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            await n8n(sql)
    assert suggestion is not None


# The admin queue (routers/suggestions.py).


async def _suggest(
    adb, kind, a, b, *, decision="same", keep="a", similarity="0.95", certainty=None
):
    """A suggestion as Workflow 2 writes it."""
    proposal = {
        "a_id": str(a),
        "b_id": str(b),
        "a_name": "model's a",
        "b_name": "model's b",
        "decision": decision,
        "keep_name": keep,
        "similarity": similarity,
    }
    if certainty:
        proposal["certainty"] = certainty
    return await adb.scalar(
        text(
            "INSERT INTO suggestions (kind, target, proposal, reason, confidence, model,"
            " prompt_version) VALUES (:k, CAST(:t AS jsonb), CAST(:p AS jsonb), 'because', 1,"
            " 'gemma4:12b', 'merge-v1') RETURNING id"
        ),
        {
            "k": kind,
            "t": json.dumps(sorted([str(a), str(b)])),
            "p": json.dumps(proposal),
        },
    )


async def _names(adb):
    rows = await adb.execute(
        text(
            "SELECT c.name, p.name FROM ingredients c"
            " LEFT JOIN ingredients p ON p.id = c.parent_id ORDER BY 1"
        )
    )
    return [tuple(r) for r in rows]


async def test_the_queue_is_for_admins_and_closest_first(people, adb) -> None:
    oats, quick, flax, golden = [
        await _ingredient(adb, n)
        for n in ("Quick-Cooking Oats", "Quick-Cook Oats", "Flax Meal", "Golden Flax Meal")
    ]
    await _suggest(adb, "parent", golden, flax, decision="a_under_b", similarity="0.81")
    await _suggest(adb, "merge", oats, quick, similarity="0.9875")
    ann = await people("ann")
    assert (await ann.get("/api/suggestions")).status_code == 403
    admin = await people("ada", admin=True)
    page = (await admin.get("/api/suggestions")).json()
    assert page["open_by_kind"] == {"merge": 1, "parent": 1}
    first, second = page["suggestions"]
    # The names are the ingredients' own, not what the model was shown.
    assert (first["a"]["name"], first["b"]["name"], first["similarity"]) == (
        "Quick-Cooking Oats",
        "Quick-Cook Oats",
        0.9875,
    )
    assert second["decision"] == "a_under_b" and second["actionable"]
    only = (await admin.get("/api/suggestions", params={"kind": "parent"})).json()
    assert [s["kind"] for s in only["suggestions"]] == ["parent"]


@pytest.mark.parametrize(
    ("keep", "kept"), [(None, "Thai Red Curry Paste"), ("b", "Red Thai Curry Paste")]
)
async def test_accepting_a_merge_keeps_the_chosen_name(people, adb, keep, kept) -> None:
    a = await _ingredient(adb, "Thai Red Curry Paste")
    b = await _ingredient(adb, "Red Thai Curry Paste")
    suggestion = await _suggest(adb, "merge", a, b, keep="a")
    admin = await people("ada", admin=True)
    body = {"keep": keep} if keep else {}
    done = await admin.post(f"/api/suggestions/{suggestion}/accept", json=body)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "accepted"
    assert await _names(adb) == [(kept, None)]
    # The dropped name still finds it.
    dropped = ({"Thai Red Curry Paste", "Red Thai Curry Paste"} - {kept}).pop()
    assert await adb.scalar(
        text("SELECT count(*) FROM ingredient_aliases WHERE name = :n"), {"n": dropped}
    )
    again = await admin.post(f"/api/suggestions/{suggestion}/accept", json={})
    assert again.status_code == 409


async def test_accepting_a_parent_puts_one_under_the_other(people, adb) -> None:
    flax = await _ingredient(adb, "Flax Meal")
    golden = await _ingredient(adb, "Golden Flax Meal")
    suggestion = await _suggest(adb, "parent", flax, golden, decision="b_under_a")
    admin = await people("ada", admin=True)
    done = await admin.post(f"/api/suggestions/{suggestion}/accept", json={})
    assert done.status_code == 200, done.text
    assert await _names(adb) == [("Flax Meal", None), ("Golden Flax Meal", "Flax Meal")]


async def test_a_parent_that_would_loop_is_refused(people, adb) -> None:
    cheese = await _ingredient(adb, "Cheese")
    cheddar = await _ingredient(adb, "Cheddar")
    await adb.execute(
        text("UPDATE ingredients SET parent_id = :p WHERE id = :i"), {"p": cheese, "i": cheddar}
    )
    suggestion = await _suggest(adb, "parent", cheese, cheddar, decision="a_under_b")
    admin = await people("ada", admin=True)
    refused = await admin.post(f"/api/suggestions/{suggestion}/accept", json={})
    assert refused.status_code == 422
    assert (
        await adb.scalar(text("SELECT status FROM suggestions WHERE id = :i"), {"i": suggestion})
        == "open"
    )


async def test_one_naming_a_gone_ingredient_can_only_be_dismissed(people, adb) -> None:
    a = await _ingredient(adb, "Salted Dried Shrimp")
    b = await _ingredient(adb, "Dried Salted Shrimp")
    suggestion = await _suggest(adb, "merge", a, b)
    await adb.execute(text("DELETE FROM ingredients WHERE id = :i"), {"i": b})
    admin = await people("ada", admin=True)
    listed = (await admin.get("/api/suggestions")).json()["suggestions"][0]
    assert not listed["actionable"]
    # The model's name stands in for the one that's gone.
    assert (listed["b"]["name"], listed["b"]["exists"]) == ("model's b", False)
    assert (await admin.post(f"/api/suggestions/{suggestion}/accept", json={})).status_code == 409
    dismissed = await admin.post(f"/api/suggestions/{suggestion}/dismiss")
    assert dismissed.json()["status"] == "dismissed"
    assert (await admin.get("/api/suggestions")).json()["total"] == 0
    decided = (await admin.get("/api/suggestions", params={"state": "decided"})).json()
    assert [s["status"] for s in decided["suggestions"]] == ["dismissed"]


async def test_certain_comes_first_then_likely_then_the_closest(people, adb) -> None:
    """merge-v2 says how sure it is in a word; merge-v1 rows don't say."""
    names = ["Oats", "Oat", "Flax", "Flaxseed", "Chile", "Chili", "Gochugaru", "Korean Chile"]
    ids = [await _ingredient(adb, n) for n in names]
    await _suggest(adb, "merge", ids[0], ids[1], similarity="0.99")  # v1: no word
    await _suggest(adb, "merge", ids[2], ids[3], similarity="0.85", certainty="likely")
    await _suggest(adb, "merge", ids[4], ids[5], similarity="0.82", certainty="certain")
    await _suggest(adb, "merge", ids[6], ids[7], similarity="0.90", certainty="likely")
    admin = await people("ada", admin=True)
    listed = (await admin.get("/api/suggestions")).json()["suggestions"]
    assert [(s["a"]["name"], s["certainty"]) for s in listed] == [
        ("Chile", "certain"),
        ("Gochugaru", "likely"),
        ("Flax", "likely"),
        ("Oats", None),
    ]


# Tag suggestions (0033): Workflow 4 suggests tags for recipes.


async def _recipe(adb, title, *, chapter=None):
    source = await adb.scalar(
        text("INSERT INTO sources (title) VALUES ('Biscuit Book') RETURNING id")
    )
    return await adb.scalar(
        text("INSERT INTO recipes (source_id, title, chapter) VALUES (:s, :t, :c) RETURNING id"),
        {"s": source, "t": title, "c": chapter},
    )


async def _tag_id(adb, name):
    return await adb.scalar(text("SELECT id FROM tags WHERE name = :n"), {"n": name})


async def _suggest_tag(adb, recipe, tag, certainty="likely"):
    proposal = {
        "recipe_id": str(recipe),
        "tag_id": str(tag),
        "recipe_title": "model's title",
        "tag_name": "model's tag",
        "certainty": certainty,
    }
    return await adb.scalar(
        text(
            "INSERT INTO suggestions (kind, target, proposal, reason, confidence, model,"
            " prompt_version) VALUES ('tag', CAST(:t AS jsonb), CAST(:p AS jsonb),"
            " 'It is a bread.', 0.6, 'gemma4:12b', 'tag-v1') RETURNING id"
        ),
        {"t": json.dumps([str(recipe), str(tag)]), "p": json.dumps(proposal)},
    )


async def test_a_tag_suggestion_is_listed_and_accepted(people, adb) -> None:
    biscuits = await _recipe(adb, "Cheddar Biscuits", chapter="Biscuits")
    bread = await _tag_id(adb, "Bread")
    suggestion = await _suggest_tag(adb, biscuits, bread)
    admin = await people("ada", admin=True)
    page = (await admin.get("/api/suggestions", params={"kind": "tag"})).json()
    assert page["open_by_kind"] == {"tag": 1}
    listed = page["suggestions"][0]
    assert (listed["recipe"]["title"], listed["recipe"]["chapter"]) == (
        "Cheddar Biscuits",
        "Biscuits",
    )
    assert (listed["tag"]["name"], listed["tag"]["kind"], listed["tag"]["already"]) == (
        "Bread",
        "course",
        False,
    )
    assert listed["actionable"] and listed["certainty"] == "likely"
    done = await admin.post(f"/api/suggestions/{suggestion}/accept", json={})
    assert done.status_code == 200, done.text
    assert done.json()["tag"]["already"]
    tags = (await admin.get(f"/api/recipes/{biscuits}")).json()["tags"]
    assert [t["name"] for t in tags] == ["Bread"]


async def test_accepting_a_tag_the_recipe_has_adds_nothing(people, adb) -> None:
    biscuits = await _recipe(adb, "Cheddar Biscuits")
    bread = await _tag_id(adb, "Bread")
    await adb.execute(
        text(
            "INSERT INTO source_tags (source_id, tag_id)"
            " SELECT source_id, :t FROM recipes WHERE id = :r"
        ),
        {"t": bread, "r": biscuits},
    )
    suggestion = await _suggest_tag(adb, biscuits, bread)
    admin = await people("ada", admin=True)
    listed = (await admin.get("/api/suggestions")).json()["suggestions"][0]
    assert listed["tag"]["already"]
    assert (await admin.post(f"/api/suggestions/{suggestion}/accept", json={})).status_code == 200
    assert await adb.scalar(text("SELECT count(*) FROM recipe_tags")) == 0


async def test_a_tag_suggestion_for_a_gone_recipe_is_only_dismissed(people, adb) -> None:
    biscuits = await _recipe(adb, "Cheddar Biscuits")
    suggestion = await _suggest_tag(adb, biscuits, await _tag_id(adb, "Bread"))
    await adb.execute(text("DELETE FROM recipes WHERE id = :r"), {"r": biscuits})
    admin = await people("ada", admin=True)
    listed = (await admin.get("/api/suggestions")).json()["suggestions"][0]
    assert not listed["actionable"]
    assert (listed["recipe"]["title"], listed["recipe"]["exists"]) == ("model's title", False)
    assert (await admin.post(f"/api/suggestions/{suggestion}/accept", json={})).status_code == 409
    dismissed = await admin.post(f"/api/suggestions/{suggestion}/dismiss")
    assert dismissed.json()["status"] == "dismissed"
