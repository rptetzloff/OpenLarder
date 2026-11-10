"""Requests for a book to be indexed (routers/book_requests.py)."""

import pytest
from sqlalchemy import text

from fake_openlibrary import PINK_CAKE
from openlarder.routers import book_requests


async def _make_contributor(adb, name: str) -> None:
    await adb.execute(
        text("UPDATE users SET role = 'contributor' WHERE display_name = :n"), {"n": name}
    )


async def test_asking_by_isbn_fills_in_the_title(client, openlib) -> None:
    r = await client.post("/api/requests", json={"isbn": "978-0-393-54111-3"})
    assert r.status_code == 200
    asked = r.json()
    assert asked["outcome"] == "created"
    assert asked["request"]["title"] == "Love Is a Pink Cake"
    assert asked["request"]["isbn13"] == PINK_CAKE
    assert asked["request"]["votes"] == 1 and asked["request"]["voted"]
    page = (await client.get("/api/requests")).json()
    assert [q["title"] for q in page["requests"]] == ["Love Is a Pink Cake"]
    assert page["counts"] == {"open": 1}


async def test_asking_needs_an_isbn_or_a_title(client) -> None:
    assert (await client.post("/api/requests", json={})).status_code == 422
    assert (await client.post("/api/requests", json={"isbn": "123"})).status_code == 422
    r = await client.post("/api/requests", json={"title": "  Jerusalem  ", "author": "Ottolenghi"})
    assert r.json()["request"]["title"] == "Jerusalem"


async def test_an_unknown_isbn_needs_a_title(client, openlib) -> None:
    r = await client.post("/api/requests", json={"isbn": "9780000000002"})
    assert r.status_code == 422 and "title" in r.json()["detail"]
    r = await client.post("/api/requests", json={"isbn": "9780000000002", "title": "Odd Book"})
    assert r.json()["outcome"] == "created"


async def test_asking_again_is_a_vote_once_per_person(client, people, openlib) -> None:
    await client.post("/api/requests", json={"isbn": PINK_CAKE})
    again = (await client.post("/api/requests", json={"isbn": PINK_CAKE})).json()
    assert again["outcome"] == "already" and again["request"]["votes"] == 1
    ann = await people("ann")
    voted = (await ann.post("/api/requests", json={"isbn": PINK_CAKE})).json()
    assert voted["outcome"] == "voted" and voted["request"]["votes"] == 2
    # By title, ignoring case.
    await ann.post("/api/requests", json={"title": "Jerusalem"})
    bo = await people("bo")
    assert (await bo.post("/api/requests", json={"title": "jerusalem"})).json()[
        "outcome"
    ] == "voted"
    rid = voted["request"]["id"]
    assert (await bo.post(f"/api/requests/{rid}/vote")).json()["votes"] == 3
    assert (await bo.post(f"/api/requests/{rid}/vote")).json()["votes"] == 3
    page = (await bo.get("/api/requests")).json()
    assert [(q["votes"], q["voted"]) for q in page["requests"]] == [(3, True), (2, True)]


async def test_a_book_already_indexed_is_pointed_to(client, adb) -> None:
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    await adb.execute(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:w, :i)"),
        {"w": work, "i": PINK_CAKE},
    )
    await adb.execute(
        text("INSERT INTO recipes (source_id, title) VALUES (:w, 'Rhubarb Cake')"), {"w": work}
    )
    r = (await client.post("/api/requests", json={"isbn": PINK_CAKE})).json()
    assert r == {"outcome": "in_catalog", "request": None, "source_id": str(work)}


async def test_a_private_collection_is_not_given_away(client, people, adb, openlib) -> None:
    """Asking for a book only in someone's private family collection says
    nothing of it: it's asked for like any other."""
    ann = await people("ann")
    owner = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'ann'"))
    work = await adb.scalar(
        text(
            "INSERT INTO sources (title, kind, private, owner_id, acknowledged_at)"
            " VALUES ('Nana''s Cards', 'family', true, :o, now()) RETURNING id"
        ),
        {"o": owner},
    )
    await adb.execute(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:w, :i)"),
        {"w": work, "i": PINK_CAKE},
    )
    await adb.execute(
        text("INSERT INTO recipes (source_id, title) VALUES (:w, 'Fudge')"), {"w": work}
    )
    r = (await client.post("/api/requests", json={"isbn": PINK_CAKE})).json()
    assert r["outcome"] == "created"
    assert r["request"]["source_id"] is None
    assert "Nana" not in str(r)
    assert ann  # signed in, unused


async def test_signed_out_asking_is_limited_and_bots_are_ignored(client, people, adb) -> None:
    for n in range(book_requests.ANONYMOUS_PER_DAY):
        assert (await client.post("/api/requests", json={"title": f"Book {n}"})).status_code == 200
    r = await client.post("/api/requests", json={"title": "One more"})
    assert r.status_code == 429 and "Sign in" in r.json()["detail"]
    ann = await people("ann")
    assert (await ann.post("/api/requests", json={"title": "One more"})).status_code == 200
    bot = await ann.post("/api/requests", json={"title": "Cheap pills", "website": "http://x"})
    assert bot.json()["outcome"] == "created"
    assert (
        await adb.scalar(text("SELECT count(*) FROM book_requests WHERE title = 'Cheap pills'"))
        == 0
    )


async def test_a_signed_out_vote_keeps_no_address(client, adb) -> None:
    await client.post("/api/requests", json={"title": "Jerusalem"})
    voters = await adb.scalar(text("SELECT string_agg(voter, ' ') FROM request_votes"))
    assert voters.startswith("ip:") and "127.0.0.1" not in voters


async def test_only_contributors_claim_and_a_claim_lapses(people, adb) -> None:
    ann, bo, cy = await people("ann"), await people("bo"), await people("cy")
    rid = (await ann.post("/api/requests", json={"title": "Jerusalem"})).json()["request"]["id"]
    r = await ann.post(f"/api/requests/{rid}/claim")
    assert r.status_code == 403 and "moderator" in r.json()["detail"]
    await _make_contributor(adb, "bo")
    await _make_contributor(adb, "cy")
    claimed = (await bo.post(f"/api/requests/{rid}/claim")).json()
    assert claimed["status"] == "claimed" and claimed["claimed_by"]["name"] == "bo"
    assert (await cy.post(f"/api/requests/{rid}/claim")).status_code == 409
    assert (await ann.get("/api/requests?state=claimed")).json()["counts"] == {"claimed": 1}
    # Thirty days quiet: open again, and cy may take it.
    await adb.execute(text("UPDATE book_requests SET active_at = now() - interval '31 days'"))
    page = (await ann.get("/api/requests")).json()
    [lapsed] = page["requests"]
    assert lapsed["status"] == "open" and lapsed["claimed_by"] is None
    assert (await cy.post(f"/api/requests/{rid}/claim")).json()["claimed_by"]["name"] == "cy"
    # Only the claimer releases it.
    assert (await bo.post(f"/api/requests/{rid}/release")).status_code == 409
    assert (await cy.post(f"/api/requests/{rid}/release")).json()["status"] == "open"


async def test_mine_is_what_i_asked_for_or_claimed(client, people, adb) -> None:
    ann, bo = await people("ann"), await people("bo")
    await _make_contributor(adb, "bo")
    a = (await ann.post("/api/requests", json={"title": "Jerusalem"})).json()["request"]
    b = (await bo.post("/api/requests", json={"title": "Plenty"})).json()["request"]
    await bo.post(f"/api/requests/{a['id']}/claim")
    mine = (await ann.get("/api/requests?state=mine")).json()["requests"]
    assert [(q["title"], q["mine"]) for q in mine] == [("Jerusalem", True)]
    bos = {q["title"] for q in (await bo.get("/api/requests?state=mine")).json()["requests"]}
    assert bos == {"Jerusalem", "Plenty"} and b
    assert (await client.get("/api/requests?state=mine")).status_code == 401


async def test_done_and_declined_close_a_request(people, adb) -> None:
    ann, ada = await people("ann"), await people("ada", admin=True)
    a = (await ann.post("/api/requests", json={"title": "Jerusalem"})).json()["request"]
    b = (await ann.post("/api/requests", json={"title": "Cheap pills"})).json()["request"]
    assert (await ann.post(f"/api/requests/{a['id']}/done", json={})).status_code == 403
    assert (
        await ann.post(f"/api/requests/{b['id']}/decline", json={"reason": "No"})
    ).status_code == 403
    done = (await ada.post(f"/api/requests/{a['id']}/done", json={})).json()
    assert done["status"] == "done"
    assert (
        await ada.post(f"/api/requests/{b['id']}/decline", json={"reason": " "})
    ).status_code == 422
    declined = (
        await ada.post(f"/api/requests/{b['id']}/decline", json={"reason": "Not a cookbook."})
    ).json()
    assert (declined["status"], declined["reason"]) == ("declined", "Not a cookbook.")
    assert (await ann.post(f"/api/requests/{a['id']}/vote")).status_code == 409
    # Asked again once closed: a new request.
    again = (await ann.post("/api/requests", json={"title": "Jerusalem"})).json()
    assert again["outcome"] == "created"
    counts = (await ann.get("/api/requests")).json()["counts"]
    assert counts == {"open": 1, "done": 1, "declined": 1}


@pytest.mark.parametrize("path", ["vote", "claim", "release"])
async def test_an_unknown_request_is_404(people, adb, path) -> None:
    ada = await people("ada", admin=True)
    r = await ada.post(f"/api/requests/00000000-0000-0000-0000-000000000000/{path}")
    assert r.status_code == 404
