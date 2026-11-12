"""Your shelf (routers/shelf.py): the books you own, and searching them."""

from sqlalchemy import text


async def _book(mo, adb, title):
    book = (await mo.post("/api/sources/manual", json={"title": title})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    return book, edition


async def _recipe(mo, book, edition, title):
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={"title": title, "editions": [{"edition_id": edition, "page": "12"}]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_a_shelf_is_its_owners(people, client, adb) -> None:
    mo, ann, bo = await people("mo", role="moderator"), await people("ann"), await people("bo")
    plenty, plenty_ed = await _book(mo, adb, "Plenty")
    jolene, jolene_ed = await _book(mo, adb, "Jolene")

    assert (await ann.put(f"/api/shelf/{plenty}", json={"edition_id": plenty_ed})).json() == {
        "source_id": plenty,
        "on_shelf": True,
        "edition_id": plenty_ed,
    }
    await ann.put(f"/api/shelf/{jolene}", json={})
    shelf = (await ann.get("/api/shelf")).json()["books"]
    assert [(b["title"], b["edition_id"]) for b in shelf] == [
        ("Jolene", None),
        ("Plenty", plenty_ed),
    ]
    assert (await ann.get(f"/api/shelf/{plenty}")).json()["edition_id"] == plenty_ed

    # Nobody else's.
    assert (await bo.get("/api/shelf")).json()["books"] == []
    assert (await bo.get(f"/api/shelf/{plenty}")).json()["on_shelf"] is False
    assert (await client.get("/api/shelf")).status_code == 401
    assert (await client.put(f"/api/shelf/{plenty}", json={})).status_code == 401

    # Another book's edition, a website, a book you can't see: refused.
    wrong = await ann.put(f"/api/shelf/{plenty}", json={"edition_id": jolene_ed})
    assert wrong.status_code == 422
    site = await adb.scalar(
        text(
            "INSERT INTO sources (title, kind, host) VALUES ('Smitten', 'website', 'smitten.com')"
            " RETURNING id"
        )
    )
    box = (
        await bo.post("/api/sources/family", json={"title": "Bo's Box", "acknowledged": True})
    ).json()["id"]
    await adb.commit()
    assert (await ann.put(f"/api/shelf/{site}", json={})).status_code == 422
    assert (await ann.put(f"/api/shelf/{box}", json={})).status_code == 404

    # Changing the edition, then taking it off.
    assert (await ann.put(f"/api/shelf/{plenty}", json={})).json()["edition_id"] is None
    assert (await ann.delete(f"/api/shelf/{plenty}")).status_code == 204
    assert [b["title"] for b in (await ann.get("/api/shelf")).json()["books"]] == ["Jolene"]


async def test_search_keeps_to_your_shelf(people, client, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    plenty, plenty_ed = await _book(mo, adb, "Plenty")
    jolene, jolene_ed = await _book(mo, adb, "Jolene")
    await _recipe(mo, plenty, plenty_ed, "Green Shakshuka")
    await _recipe(mo, jolene, jolene_ed, "Red Shakshuka")

    empty = (await ann.get("/api/search", params={"q": "shakshuka", "shelf": True})).json()
    assert (empty["shelf_books"], empty["total"]) == (0, 0)

    await ann.put(f"/api/shelf/{plenty}", json={})
    found = (await ann.get("/api/search", params={"q": "shakshuka", "shelf": True})).json()
    assert found["shelf_books"] == 1
    assert [r["title"] for r in found["recipes"]] == ["Green Shakshuka"]
    every = (await ann.get("/api/search", params={"q": "shakshuka"})).json()
    assert every["total"] == 2 and every["shelf_books"] is None
    signed_out = await client.get("/api/search", params={"q": "shakshuka", "shelf": True})
    assert signed_out.status_code == 401


async def test_a_merge_takes_shelves_with_it(people, adb) -> None:
    mo, ad = await people("mo", role="moderator"), await people("ad", role="admin")
    ann, bo = await people("ann"), await people("bo")
    kept, _ = await _book(mo, adb, "Plenty")
    gone, gone_ed = await _book(mo, adb, "Plenty (paperback)")
    await ann.put(f"/api/shelf/{gone}", json={"edition_id": gone_ed})
    # Bo has both: one is kept, with the edition said for the other.
    await bo.put(f"/api/shelf/{kept}", json={})
    await bo.put(f"/api/shelf/{gone}", json={"edition_id": gone_ed})

    assert (await mo.post(f"/api/sources/{gone}/merge", json={"into": kept})).status_code == 200
    for who in (ann, bo):
        assert [
            (b["id"], b["edition_id"]) for b in (await who.get("/api/shelf")).json()["books"]
        ] == [(kept, gone_ed)]

    [merge] = (await ad.get("/api/merges")).json()
    assert (await ad.post(f"/api/merges/{merge['id']}/unmerge")).status_code == 200
    # Their edition went back, and the shelves with it.
    assert [b["id"] for b in (await ann.get("/api/shelf")).json()["books"]] == [gone]


async def test_deleting_the_account_empties_the_shelf(people, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    plenty, _ = await _book(mo, adb, "Plenty")
    await ann.put(f"/api/shelf/{plenty}", json={})
    assert (await ann.post("/api/account/delete", json={"confirm": "ann"})).status_code == 204
    assert await adb.scalar(text("SELECT count(*) FROM shelf_books")) == 0
