"""Reports: "Report a problem" on public records (routers/reports.py)."""

from sqlalchemy import text

from openlarder.routers import reports


async def _recipe(mo, adb, title="Shakshuka"):
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": []})).json()[
        "id"
    ]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={"title": title, "editions": [{"edition_id": edition}], "ingredients": ["eggs"]},
    )
    return book, r.json()["id"]


async def test_anyone_reports_and_a_moderator_resolves(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    book, recipe = await _recipe(mo, adb)
    r = await client.post(
        "/api/reports",
        json={"kind": "recipe", "id": recipe, "reason": "wrong", "note": "  It's on page 14. "},
    )
    assert r.status_code == 201, r.text
    ann = await people("ann")
    await ann.post("/api/reports", json={"kind": "source", "id": book, "reason": "duplicate"})
    await ann.post("/api/reports", json={"kind": "recipe", "id": recipe, "reason": "copied"})
    assert (await ann.get("/api/admin/reports")).status_code == 403
    page = (await mo.get("/api/admin/reports")).json()
    assert page["counts"] == {"open": 3}
    first = page["reports"][0]
    assert (first["kind"], first["title"], first["note"], first["by"], first["others"]) == (
        "recipe",
        "Shakshuka",
        "It's on page 14.",
        None,
        1,
    )
    assert first["href"] == f"/recipes/{recipe}"
    assert page["reports"][1]["by"] == "ann"
    r = await mo.post(
        f"/api/admin/reports/{first['id']}", json={"action": "resolve", "note": "Fixed the page."}
    )
    assert r.status_code == 204
    done = (await mo.get("/api/admin/reports", params={"state": "resolved"})).json()["reports"]
    assert [(d["resolution"], d["status"]) for d in done] == [("Fixed the page.", "resolved")]
    assert (
        await mo.post(f"/api/admin/reports/{first['id']}", json={"action": "dismiss"})
    ).status_code == 404


async def test_reporting_again_replaces_the_open_one(people, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    _, recipe = await _recipe(mo, adb)
    await ann.post("/api/reports", json={"kind": "recipe", "id": recipe, "reason": "wrong"})
    await ann.post(
        "/api/reports",
        json={"kind": "recipe", "id": recipe, "reason": "spam", "note": "Actually spam"},
    )
    [only] = (await mo.get("/api/admin/reports")).json()["reports"]
    assert (only["reason"], only["note"]) == ("spam", "Actually spam")


async def test_what_cant_be_reported(people, client, adb) -> None:
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    ).json()["id"]
    assert (
        await client.post("/api/reports", json={"kind": "source", "id": box, "reason": "spam"})
    ).status_code == 404
    gone = "00000000-0000-0000-0000-000000000000"
    assert (
        await client.post("/api/reports", json={"kind": "recipe", "id": gone, "reason": "wrong"})
    ).status_code == 404
    bad = await client.post("/api/reports", json={"kind": "user", "id": gone, "reason": "wrong"})
    assert bad.status_code == 422


async def test_signed_out_reports_are_limited_and_keep_no_address(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    _, recipe = await _recipe(mo, adb)
    for _ in range(reports.ANONYMOUS_PER_DAY):
        r = await client.post(
            "/api/reports", json={"kind": "recipe", "id": recipe, "reason": "wrong"}
        )
        assert r.status_code == 201
    r = await client.post("/api/reports", json={"kind": "recipe", "id": recipe, "reason": "wrong"})
    assert r.status_code == 429 and "Sign in" in r.json()["detail"]
    kept = await adb.scalar(text("SELECT string_agg(reporter, ' ') FROM reports"))
    assert kept.startswith("ip:") and "127.0.0.1" not in kept
    bot = await (await people("ann")).post(
        "/api/reports", json={"kind": "recipe", "id": recipe, "reason": "spam", "website": "x"}
    )
    assert bot.status_code == 201
    assert await adb.scalar(text("SELECT count(*) FROM reports WHERE reason = 'spam'")) == 0


async def test_a_report_outlives_its_record(people, adb) -> None:
    mo = await people("mo", role="moderator")
    _, recipe = await _recipe(mo, adb)
    await mo.post("/api/reports", json={"kind": "recipe", "id": recipe, "reason": "duplicate"})
    await mo.delete(f"/api/recipes/{recipe}")
    [left] = (await mo.get("/api/admin/reports")).json()["reports"]
    assert (left["title"], left["href"]) == (None, None)
