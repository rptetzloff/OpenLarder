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
