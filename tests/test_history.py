"""Edit history (migration 0040, history.py)."""

from sqlalchemy import text


async def _revisions(adb, where="true", **params):
    rows = await adb.execute(
        text(
            "SELECT r.table_name, r.action, r.changes, u.display_name, r.change_id, r.family,"
            " r.source_id, r.recipe_id"
            f" FROM revisions r LEFT JOIN users u ON u.id = r.user_id WHERE {where} ORDER BY r.id"
        ),
        params,
    )
    return rows.mappings().all()


async def test_a_save_is_one_change_by_whoever_made_it(people, adb) -> None:
    mo = await people("mo", role="moderator")
    book = (
        await mo.post(
            "/api/sources/manual", json={"title": "Plenty", "authors": ["Yotam Ottolenghi"]}
        )
    ).json()
    revs = await _revisions(adb)
    assert {r["display_name"] for r in revs} == {"mo"}
    assert len({r["change_id"] for r in revs}) == 1
    tables = {r["table_name"] for r in revs}
    assert {"sources", "authors", "source_credits"} <= tables
    [src] = [r for r in revs if r["table_name"] == "sources" and r["action"] == "i"]
    assert src["action"] == "i" and src["changes"]["title"] == [None, "Plenty"]
    assert "created_at" not in src["changes"] and not src["family"]

    await mo.put(
        f"/api/sources/{book['id']}", json={"title": "Plenty More", "authors": ["Yotam Ottolenghi"]}
    )
    [edit] = await _revisions(adb, "table_name = 'sources' AND action = 'u' AND changes ? 'title'")
    assert edit["changes"]["title"] == ["Plenty", "Plenty More"]
    assert edit["change_id"] != src["change_id"]


async def test_a_recipe_and_its_lines_belong_to_its_source(people, adb) -> None:
    mo = await people("mo", role="moderator")
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": []})).json()
    edition = await adb.scalar(
        text("SELECT id FROM editions WHERE source_id = :s"), {"s": book["id"]}
    )
    recipe = (
        await mo.post(
            f"/api/sources/{book['id']}/recipes",
            json={
                "title": "Shakshuka",
                "editions": [{"edition_id": str(edition)}],
                "ingredients": ["eggs", "tomatoes"],
            },
        )
    ).json()
    lines = await _revisions(adb, "table_name = 'recipe_ingredients'")
    assert len(lines) == 2
    assert {str(r["source_id"]) for r in lines} == {book["id"]}
    assert {str(r["recipe_id"]) for r in lines} == {recipe["id"]}
    await mo.delete(f"/api/recipes/{recipe['id']}")
    gone = await _revisions(adb, "action = 'd' AND table_name = 'recipe_ingredients'")
    assert len(gone) == 2 and {str(r["source_id"]) for r in gone} == {book["id"]}


async def test_a_family_collection_is_marked(people, adb) -> None:
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Gran's Box", "acknowledged": True})
    ).json()
    await ann.post(
        f"/api/sources/{box['id']}/recipes", json={"title": "Fudge", "ingredients": ["sugar"]}
    )
    revs = await _revisions(adb, "table_name IN ('sources', 'recipes', 'recipe_ingredients')")
    assert revs and all(r["family"] for r in revs)


async def test_sql_by_hand_is_recorded_without_anyone(adb) -> None:
    await adb.execute(text("INSERT INTO tags (kind, name) VALUES ('course', 'Breakfast-ish')"))
    [rev] = await _revisions(adb, "table_name = 'tags'")
    assert rev["display_name"] is None and rev["changes"]["name"] == [None, "Breakfast-ish"]


async def test_a_change_to_nothing_but_noise_is_not_recorded(adb) -> None:
    await adb.execute(text("INSERT INTO tags (kind, name) VALUES ('course', 'Brunch2')"))
    await adb.execute(
        text("UPDATE tags SET updated_at = now() + interval '1 day' WHERE name = 'Brunch2'")
    )
    assert len(await _revisions(adb, "table_name = 'tags'")) == 1


# Reading it


async def _book_with_recipe(mo, adb, title="Plenty"):
    book = (
        await mo.post("/api/sources/manual", json={"title": title, "authors": ["Yotam Ottolenghi"]})
    ).json()
    edition = await adb.scalar(
        text("SELECT id FROM editions WHERE source_id = :s"), {"s": book["id"]}
    )
    recipe = (
        await mo.post(
            f"/api/sources/{book['id']}/recipes",
            json={
                "title": "Shakshuka",
                "editions": [{"edition_id": str(edition)}],
                "ingredients": ["eggs"],
            },
        )
    ).json()
    return book["id"], recipe["id"]


async def test_a_record_shows_its_history_to_anyone(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book, recipe = await _book_with_recipe(mo, adb)
    edition = await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    r = await mo.put(
        f"/api/recipes/{recipe}",
        json={
            "title": "Green Shakshuka",
            "editions": [{"edition_id": str(edition)}],
            "ingredients": ["eggs"],
        },
    )
    assert r.status_code == 200, r.text
    changes = (await client.get(f"/api/recipes/{recipe}/history")).json()
    assert [c["by"] for c in changes] == ["mo", "mo"]
    newest = changes[0]["entries"]
    [title] = [e for e in newest if e["what"] == "recipe"]
    assert title["action"] == "changed"
    assert {"field": "title", "before": "Shakshuka", "after": "Green Shakshuka"} in title["fields"]
    whole = (await client.get(f"/api/sources/{book}/history")).json()
    assert {e["what"] for c in whole for e in c["entries"]} >= {
        "source",
        "credit",
        "recipe",
        "ingredient line",
    }
    eggs = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'eggs'"))
    named = (await client.get(f"/api/ingredients/{eggs}/history")).json()
    assert named and named[0]["entries"][0]["what"] == "ingredient"
    author = await adb.scalar(text("SELECT id FROM authors WHERE name = 'Yotam Ottolenghi'"))
    assert (await client.get(f"/api/authors/{author}/history")).json()


async def test_a_private_collections_history_is_its_owners(people, client, adb) -> None:
    ann, bo = await people("ann"), await people("bo")
    mo = await people("mo", role="moderator")
    box = (
        await ann.post("/api/sources/family", json={"title": "Gran's Box", "acknowledged": True})
    ).json()["id"]
    made = await ann.post(
        f"/api/sources/{box}/recipes", json={"title": "Fudge", "ingredients": ["secret spice"]}
    )
    recipe = made.json()["id"]
    assert (await ann.get(f"/api/sources/{box}/history")).json()
    for other in (client, bo, mo):
        assert (await other.get(f"/api/sources/{box}/history")).status_code == 404
        assert (await other.get(f"/api/recipes/{recipe}/history")).status_code == 404
    spice = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'secret spice'"))
    assert (await bo.get(f"/api/ingredients/{spice}/history")).status_code == 404
    # A moderator's latest changes leave the collection out altogether.
    listed = (await mo.get("/api/changes")).json()
    assert (
        "Gran" not in str(listed)
        and "secret spice" not in str(listed)
        and "Fudge" not in str(listed)
    )


async def test_an_ingredient_first_named_in_private_withholds_who(people, adb) -> None:
    """Once a public recipe uses it, its history shows, but not that ann
    made it in her private collection."""
    ann, mo = await people("ann"), await people("mo", role="moderator")
    box = (
        await ann.post("/api/sources/family", json={"title": "Gran's Box", "acknowledged": True})
    ).json()["id"]
    await ann.post(
        f"/api/sources/{box}/recipes", json={"title": "Fudge", "ingredients": ["muscovado"]}
    )
    await _book_with_recipe(mo, adb)
    book = await adb.scalar(text("SELECT id FROM sources WHERE title = 'Plenty'"))
    edition = await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Cake",
            "editions": [{"edition_id": str(edition)}],
            "ingredients": ["muscovado"],
        },
    )
    muscovado = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'muscovado'"))
    [made] = (await mo.get(f"/api/ingredients/{muscovado}/history")).json()
    assert made["withheld"] and made["by"] is None and made["source_id"] is None
    assert made["entries"][0]["action"] == "added"
    # Its owner sees it was hers.
    [own] = (await ann.get(f"/api/ingredients/{muscovado}/history")).json()
    assert own["by"] == "ann" and not own["withheld"]


async def test_recent_changes_are_for_moderators(people, adb) -> None:
    mo, bo = await people("mo", role="moderator"), await people("bo", role="contributor")
    await _book_with_recipe(mo, adb)
    assert (await bo.get("/api/changes")).status_code == 403
    listed = (await mo.get("/api/changes")).json()
    assert listed and all(c["by"] == "mo" for c in listed)
    assert (await mo.get("/api/changes?by=nobody")).json() == []


async def test_an_import_is_marked(people, adb) -> None:
    ad = await people("ad", admin=True)
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    await adb.execute(text("INSERT INTO editions (source_id) VALUES (:b)"), {"b": book})
    run = (
        await ad.post("/api/import/runs", json={"books_in_list": 1, "recipes_in_file": 1})
    ).json()
    item = {"row": 2, "source_id": str(book), "title": "Rhubarb Cake", "ingredients": ["rhubarb"]}
    r = await ad.post("/api/import/recipes", json={"run_id": run["id"], "items": [item]})
    assert r.status_code == 200, r.text
    vias = set(
        await adb.scalars(text("SELECT DISTINCT via FROM revisions WHERE table_name = 'recipes'"))
    )
    assert vias == {f"import:{run['id']}"}


async def test_a_row_filled_in_by_the_same_save_reads_as_one_addition(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    _, recipe = await _book_with_recipe(mo, adb)
    [made] = (await client.get(f"/api/recipes/{recipe}/history")).json()
    assert not [e for e in made["entries"] if e["action"] == "changed"]
    [choice] = [e for e in made["entries"] if e["what"] == "ingredient choice"]
    assert {"field": "ingredient_id", "before": None, "after": "eggs"} in choice["fields"]


async def test_a_change_names_what_it_changed(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    _, recipe = await _book_with_recipe(mo, adb)
    eggs = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'eggs'"))
    # By hand, as its own change (in production, its own transaction).
    await adb.execute(text("SELECT set_config('openlarder.change', gen_random_uuid()::text, true)"))
    await adb.execute(
        text("UPDATE ingredients SET shopping_term = 'eggs, large' WHERE id = :i"), {"i": eggs}
    )
    [changed, _] = (await client.get(f"/api/ingredients/{eggs}/history")).json()
    assert changed["entries"][0]["name"] == "eggs"
