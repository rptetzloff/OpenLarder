"""Merging two records of one book (book_merge.py)."""

from sqlalchemy import text


async def _book(mo, adb, title, authors=(), isbn=None):
    body = {"title": title, "authors": list(authors)}
    if isbn:
        body["isbn"] = isbn
    book = (await mo.post("/api/sources/manual", json=body)).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    return book, edition


async def _recipe(mo, book, edition, title, page, lines=("eggs",)):
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": title,
            "editions": [{"edition_id": edition, "page": page}],
            "ingredients": list(lines),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_everything_moves_to_the_book_kept(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    kept, kept_edition = await _book(mo, adb, "Plenty", ["Yotam Ottolenghi"], "9780393541113")
    gone, gone_edition = await _book(
        mo, adb, "Plenty (paperback)", ["Yotam Ottolenghi", "Jonathan Lovekin"]
    )
    await _recipe(mo, kept, kept_edition, "Shakshuka", "12")
    moved = await _recipe(mo, gone, gone_edition, "Green Couscous", "40")
    await adb.execute(
        text("UPDATE sources SET subtitle = 'Vibrant Vegetable Recipes' WHERE id = :g"), {"g": gone}
    )
    plan = (await mo.get(f"/api/sources/{gone}/merge", params={"into": kept})).json()
    assert plan == {"editions": 1, "recipes": 1, "credits": 2, "same_titles": []}
    r = await mo.post(f"/api/sources/{gone}/merge", json={"into": kept})
    assert r.status_code == 200 and r.json()["id"] == kept
    assert (await client.get(f"/api/sources/{gone}")).status_code == 404
    book = (await client.get(f"/api/sources/{kept}")).json()
    assert sorted(r["title"] for r in book["recipes"]) == ["Green Couscous", "Shakshuka"]
    assert sorted(e["id"] for e in book["editions"]) == sorted([kept_edition, gone_edition])
    assert [c["credited_as"] for c in book["credits"]] == ["Yotam Ottolenghi", "Jonathan Lovekin"]
    assert book["subtitle"] == "Vibrant Vegetable Recipes"
    recipe = (await client.get(f"/api/recipes/{moved}")).json()
    assert recipe["source"]["id"] == kept
    assert [(p["edition_id"], p["page"]) for p in recipe["pages"]] == [(gone_edition, "40")]
    newest = (await client.get(f"/api/sources/{kept}/history")).json()[0]
    assert newest["by"] == "mo" and newest["via"] == f"merge:{gone}"


async def test_the_plan_warns_of_the_same_recipe_twice(people, adb) -> None:
    mo = await people("mo", role="moderator")
    kept, ke = await _book(mo, adb, "Plenty")
    gone, ge = await _book(mo, adb, "Plenty again")
    await _recipe(mo, kept, ke, "Shakshuka", "12")
    await _recipe(mo, gone, ge, "shakshuka", "14")
    plan = (await mo.get(f"/api/sources/{gone}/merge", params={"into": kept})).json()
    assert plan["same_titles"] == ["shakshuka"]


async def test_requests_and_proposals_follow(people, client, adb, openlib) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    kept, _ = await _book(mo, adb, "Plenty")
    gone, ge = await _book(mo, adb, "Plenty two")
    await adb.execute(
        text("INSERT INTO book_requests (title, source_id, status) VALUES ('Plenty', :g, 'done')"),
        {"g": gone},
    )
    p = await con.post(
        f"/api/sources/{gone}/proposals", json={"title": "Plenty Two", "credits": []}
    )
    assert p.status_code == 201, p.text
    await mo.post(f"/api/sources/{gone}/merge", json={"into": kept})
    assert await adb.scalar(text("SELECT source_id FROM book_requests")) == __import__("uuid").UUID(
        kept
    )
    [mine] = (await con.get("/api/account/proposals")).json()
    assert mine["status"] == "declined" and "merged into" in mine["note"]


async def test_who_and_what_can_be_merged(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    kept, _ = await _book(mo, adb, "Plenty")
    gone, _ = await _book(mo, adb, "Plenty two")
    assert (await con.post(f"/api/sources/{gone}/merge", json={"into": kept})).status_code == 403
    assert (await mo.post(f"/api/sources/{gone}/merge", json={"into": gone})).status_code == 422
    site = (
        await mo.post(
            "/api/sources/websites", json={"address": "https://example.com", "name": "Ex"}
        )
    ).json()["id"]
    assert (await mo.post(f"/api/sources/{gone}/merge", json={"into": site})).status_code == 422
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    assert (await mo.post(f"/api/sources/{gone}/merge", json={"into": box})).status_code == 404


async def _merges(ad) -> list[dict]:
    r = await ad.get("/api/merges")
    assert r.status_code == 200, r.text
    return r.json()


async def test_an_administrator_unmerges(people, client, adb, openlib) -> None:
    """Ray, 2026-11-11: "even if admin only as a check on moderators"."""
    mo, ad = await people("mo", role="moderator"), await people("ad", role="admin")
    con = await people("con", role="contributor")
    kept, kept_edition = await _book(mo, adb, "Plenty", ["Yotam Ottolenghi"], "9780393541113")
    gone, gone_edition = await _book(
        mo, adb, "Plenty (paperback)", ["Yotam Ottolenghi", "Jonathan Lovekin"]
    )
    await _recipe(mo, kept, kept_edition, "Shakshuka", "12")
    moved = await _recipe(mo, gone, gone_edition, "Green Couscous", "40")
    await adb.execute(
        text("UPDATE sources SET subtitle = 'Vibrant Vegetable Recipes' WHERE id = :g"), {"g": gone}
    )
    tags = list(await adb.scalars(text("SELECT id FROM tags ORDER BY id LIMIT 2")))
    await adb.execute(
        text("INSERT INTO source_tags (source_id, tag_id) VALUES (:g, :a), (:g, :b), (:k, :b)"),
        {"g": gone, "k": kept, "a": tags[0], "b": tags[1]},
    )
    await adb.execute(
        text("INSERT INTO book_requests (title, source_id, status) VALUES ('P', :g, 'done')"),
        {"g": gone},
    )
    p = await con.post(f"/api/sources/{gone}/proposals", json={"title": "Plenty 2", "credits": []})
    assert p.status_code == 201, p.text
    before = (await client.get(f"/api/sources/{gone}")).json()

    assert (await mo.post(f"/api/sources/{gone}/merge", json={"into": kept})).status_code == 200
    # Added to the kept book since: stays with it.
    later = await _recipe(mo, kept, kept_edition, "Later", "90")
    [merge] = await _merges(ad)
    assert merge["gone"] == {"id": gone, "title": "Plenty (paperback)"}
    assert merge["kept"]["id"] == kept and merge["merged_by"] == "mo"
    assert (merge["editions"], merge["recipes"], merge["undone_at"]) == (1, 1, None)

    # Not a moderator's to do.
    assert (await mo.post(f"/api/merges/{merge['id']}/unmerge")).status_code == 403
    r = await ad.post(f"/api/merges/{merge['id']}/unmerge")
    assert r.status_code == 200 and r.json()["id"] == gone, r.text

    back = (await client.get(f"/api/sources/{gone}")).json()
    for field in ("title", "subtitle", "credits", "editions"):
        assert back[field] == before[field], field
    assert [x["title"] for x in back["recipes"]] == ["Green Couscous"]
    recipe = (await client.get(f"/api/recipes/{moved}")).json()
    assert recipe["source"]["id"] == gone
    assert [(x["edition_id"], x["page"]) for x in recipe["pages"]] == [(gone_edition, "40")]
    book = (await client.get(f"/api/sources/{kept}")).json()
    assert sorted(x["title"] for x in book["recipes"]) == ["Later", "Shakshuka"]
    assert [c["credited_as"] for c in book["credits"]] == ["Yotam Ottolenghi"]
    assert book["subtitle"] is None
    assert (await client.get(f"/api/recipes/{later}")).json()["source"]["id"] == kept
    assert set(
        await adb.scalars(text("SELECT tag_id FROM source_tags WHERE source_id = :g"), {"g": gone})
    ) == set(tags)
    assert str(await adb.scalar(text("SELECT source_id FROM book_requests"))) == gone
    [mine] = (await con.get("/api/account/proposals")).json()
    assert mine["status"] == "open" and mine["note"] is None
    newest = (await client.get(f"/api/sources/{gone}/history")).json()[0]
    assert newest["by"] == "ad" and newest["via"] == f"unmerge:{gone}"

    [merge] = await _merges(ad)
    assert merge["undone_by"] == "ad" and merge["undone_at"]
    again = await ad.post(f"/api/merges/{merge['id']}/unmerge")
    assert again.status_code == 409 and "already" in again.json()["detail"]
    # And it can be merged again.
    assert (await mo.post(f"/api/sources/{gone}/merge", json={"into": kept})).status_code == 200
    assert len(await _merges(ad)) == 2


async def test_unmerging_is_refused_when_a_page_joins_the_books(people, client, adb) -> None:
    mo, ad = await people("mo", role="moderator"), await people("ad", role="admin")
    kept, kept_edition = await _book(mo, adb, "Plenty")
    gone, gone_edition = await _book(mo, adb, "Plenty again")
    moved = await _recipe(mo, gone, gone_edition, "Couscous", "40")
    await mo.post(f"/api/sources/{gone}/merge", json={"into": kept})
    # The moved recipe given a page in the kept book's edition too.
    await adb.execute(
        text(
            "INSERT INTO recipe_locations (source_id, recipe_id, edition_id, page)"
            " VALUES (:k, :r, :e, '41')"
        ),
        {"k": kept, "r": moved, "e": kept_edition},
    )
    [merge] = await _merges(ad)
    r = await ad.post(f"/api/merges/{merge['id']}/unmerge")
    assert r.status_code == 409 and "“Couscous”" in r.json()["detail"]
    assert (await client.get(f"/api/sources/{gone}")).status_code == 404


async def test_undo_points_a_merge_to_unmerge(people, adb) -> None:
    mo = await people("mo", role="moderator")
    kept, _ = await _book(mo, adb, "Plenty")
    gone, _ = await _book(mo, adb, "Plenty again")
    await mo.post(f"/api/sources/{gone}/merge", json={"into": kept})
    change = await adb.scalar(
        text("SELECT change_id FROM revisions WHERE via = :v LIMIT 1"), {"v": f"merge:{gone}"}
    )
    r = await mo.post(f"/api/changes/{change}/revert")
    assert r.status_code == 409 and "unmerging" in r.json()["detail"]
