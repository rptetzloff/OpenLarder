"""A book you want (routers/shelf.py; migration 0078): a second state of the
shelf, beside a book you have. *Ray, 2026-11-14.*"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from test_larder import _group_of
from test_shelf import _book, _recipe, _user_id


async def _shelf(who) -> list[tuple[str, str]]:
    books = (await who.get("/api/shelf")).json()["books"]
    return [(b["title"], b["state"]) for b in books]


async def test_a_book_is_wanted_or_had_never_both(people, adb) -> None:
    mo, ann, bo = await people("mo", role="moderator"), await people("ann"), await people("bo")
    plenty, plenty_ed = await _book(mo, adb, "Plenty")
    jolene, _ = await _book(mo, adb, "Jolene")

    wanted = await ann.put(f"/api/shelf/{plenty}", json={"state": "want"})
    assert wanted.status_code == 200, wanted.text
    assert wanted.json() == {
        "source_id": plenty,
        "on_shelf": False,
        "wanted": True,
        "edition_id": None,
        "others": [],
    }
    await ann.put(f"/api/shelf/{jolene}", json={})
    assert await _shelf(ann) == [("Jolene", "have"), ("Plenty", "want")]
    # Nobody else's.
    assert (await bo.get(f"/api/shelf/{plenty}")).json()["wanted"] is False

    # She has it now, and says which edition: the one row changes.
    had = (await ann.put(f"/api/shelf/{plenty}", json={"edition_id": plenty_ed})).json()
    assert (had["on_shelf"], had["wanted"], had["edition_id"]) == (True, False, plenty_ed)
    assert await _shelf(ann) == [("Jolene", "have"), ("Plenty", "have")]
    assert await adb.scalar(text("SELECT count(*) FROM shelf_books")) == 2

    # And back to wanting it (she gave it away): the edition goes.
    again = (await ann.put(f"/api/shelf/{plenty}", json={"state": "want"})).json()
    assert (again["on_shelf"], again["wanted"], again["edition_id"]) == (False, True, None)
    # Taken off, it's neither.
    assert (await ann.delete(f"/api/shelf/{plenty}")).status_code == 204
    off = (await ann.get(f"/api/shelf/{plenty}")).json()
    assert (off["on_shelf"], off["wanted"]) == (False, False)


async def test_a_wanted_book_takes_no_edition(people, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    plenty, plenty_ed = await _book(mo, adb, "Plenty")
    wanted = await ann.put(f"/api/shelf/{plenty}", json={"state": "want", "edition_id": plenty_ed})
    assert wanted.status_code == 200 and wanted.json()["edition_id"] is None
    # Nor will the database have one, whatever writes it.
    with pytest.raises(DBAPIError):
        async with adb.begin_nested():
            await adb.execute(
                text("UPDATE shelf_books SET edition_id = :e WHERE source_id = :s"),
                {"e": plenty_ed, "s": plenty},
            )
    with pytest.raises(DBAPIError):
        async with adb.begin_nested():
            await adb.execute(
                text("UPDATE shelf_books SET state = 'borrowed' WHERE source_id = :s"),
                {"s": plenty},
            )


async def test_a_state_that_isnt_one_is_refused(people, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    plenty, _ = await _book(mo, adb, "Plenty")
    assert (await ann.put(f"/api/shelf/{plenty}", json={"state": "borrowed"})).status_code == 422
    assert await _shelf(ann) == []


async def test_only_a_book_can_be_wanted_and_only_one_you_can_see(people, adb) -> None:
    ann, bo = await people("ann"), await people("bo")
    site = await adb.scalar(
        text(
            "INSERT INTO sources (title, kind, host) VALUES ('Smitten', 'website', 'smitten.com')"
            " RETURNING id"
        )
    )
    box = (
        await bo.post("/api/sources/family", json={"title": "Bo's Box", "acknowledged": True})
    ).json()["id"]
    assert (await ann.put(f"/api/shelf/{site}", json={"state": "want"})).status_code == 422
    assert (await ann.put(f"/api/shelf/{box}", json={"state": "want"})).status_code == 404


async def test_search_with_your_shelf_leaves_wanted_books_out(people, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    plenty, plenty_ed = await _book(mo, adb, "Plenty")
    jolene, jolene_ed = await _book(mo, adb, "Jolene")
    await _recipe(mo, plenty, plenty_ed, "Green Shakshuka")
    await _recipe(mo, jolene, jolene_ed, "Red Shakshuka")
    await ann.put(f"/api/shelf/{plenty}", json={})
    await ann.put(f"/api/shelf/{jolene}", json={"state": "want"})

    found = (await ann.get("/api/search", params={"q": "shakshuka", "shelf": True})).json()
    # The count beside "Only books on my shelf" is of the books she has.
    assert found["shelf_books"] == 1
    assert [r["title"] for r in found["recipes"]] == ["Green Shakshuka"]

    # Once she has it, it's in.
    await ann.put(f"/api/shelf/{jolene}", json={})
    found = (await ann.get("/api/search", params={"q": "shakshuka", "shelf": True})).json()
    assert found["shelf_books"] == 2 and found["total"] == 2

    # With only wanted books, the shelf is empty as far as search goes.
    await ann.put(f"/api/shelf/{plenty}", json={"state": "want"})
    await ann.put(f"/api/shelf/{jolene}", json={"state": "want"})
    empty = (await ann.get("/api/search", params={"q": "shakshuka", "shelf": True})).json()
    assert (empty["shelf_books"], empty["total"]) == (0, 0)


async def test_wanted_books_are_shared_with_the_shelf(people, adb) -> None:
    mo = await people("mo", role="moderator")
    ann, bob, cy, dee = (
        await people("ann"),
        await people("bob"),
        await people("cy"),
        await people("dee"),
    )
    ann_id = await _user_id(adb, "ann")
    group = await _group_of(ann, (bob, "view"), (cy, "edit"))
    plenty, plenty_ed = await _book(mo, adb, "Plenty")
    await _recipe(mo, plenty, plenty_ed, "Green Shakshuka")
    await ann.put(f"/api/shelf/{plenty}", json={"state": "want"})

    # Not shared: nobody sees what she wants.
    [unshared] = (await bob.get(f"/api/shelf/{plenty}")).json()["others"] or [None]
    assert unshared is None
    await ann.put("/api/shelf/groups", json={"groups": [group]})

    [seen] = (await bob.get("/api/shelf")).json()["shared"]
    assert [(b["title"], b["state"]) for b in seen["books"]] == [("Plenty", "want")]
    [other] = (await bob.get(f"/api/shelf/{plenty}")).json()["others"]
    assert (other["owner_name"], other["on_shelf"], other["wanted"]) == ("ann", False, True)
    assert (await dee.get(f"/api/shelf/{plenty}")).json()["others"] == []
    # A book she only wants isn't one the household has: not in his search.
    found = (await bob.get("/api/search", params={"q": "shakshuka", "shelf": True})).json()
    assert (found["shelf_books"], found["total"]) == (0, 0)

    # A viewer can't change it; an editor can say she has it now, or take it off.
    whose = {"owner": ann_id}
    assert (await bob.put(f"/api/shelf/{plenty}", params=whose, json={})).status_code == 403
    got = await cy.put(f"/api/shelf/{plenty}", params=whose, json={"edition_id": plenty_ed})
    assert got.status_code == 200
    assert await _shelf(ann) == [("Plenty", "have")]
    found = (await bob.get("/api/search", params={"q": "shakshuka", "shelf": True})).json()
    assert found["shelf_books"] == 1


async def test_a_merge_keeps_a_book_had_over_one_wanted(people, adb) -> None:
    mo = await people("mo", role="moderator")
    ann, bo, cy = await people("ann"), await people("bo"), await people("cy")
    kept, _ = await _book(mo, adb, "Plenty")
    gone, gone_ed = await _book(mo, adb, "Plenty (paperback)")
    # Ann wants the one kept and has the one that goes: she has it.
    await ann.put(f"/api/shelf/{kept}", json={"state": "want"})
    await ann.put(f"/api/shelf/{gone}", json={"edition_id": gone_ed})
    # Bo has the one kept and wants the other: he has it still.
    await bo.put(f"/api/shelf/{kept}", json={})
    await bo.put(f"/api/shelf/{gone}", json={"state": "want"})
    # Cy wants the one that goes: he wants the one kept.
    await cy.put(f"/api/shelf/{gone}", json={"state": "want"})

    merged = await mo.post(f"/api/sources/{gone}/merge", json={"into": kept})
    assert merged.status_code == 200, merged.text
    for who, state, edition in ((ann, "have", gone_ed), (bo, "have", None), (cy, "want", None)):
        books = (await who.get("/api/shelf")).json()["books"]
        assert [(b["id"], b["state"], b["edition_id"]) for b in books] == [(kept, state, edition)]


async def test_what_was_on_a_shelf_before_is_a_book_had(adb) -> None:
    """The migration's default: a row written without a state, as every row
    before it was."""
    user = await adb.scalar(
        text("INSERT INTO users (issuer, subject) VALUES ('test', 'before') RETURNING id")
    )
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Plenty') RETURNING id"))
    await adb.execute(
        text("INSERT INTO shelf_books (user_id, source_id) VALUES (:u, :b)"),
        {"u": user, "b": book},
    )
    assert await adb.scalar(text("SELECT state FROM shelf_books")) == "have"
