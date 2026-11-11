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


async def _book(adb, title: str, isbn13: str | None = None, review: str = "published"):
    work = await adb.scalar(
        text("INSERT INTO sources (title, review) VALUES (:t, :r) RETURNING id"),
        {"t": title, "r": review},
    )
    if isbn13:
        await adb.execute(
            text("INSERT INTO editions (source_id, isbn13) VALUES (:w, :i)"),
            {"w": work, "i": isbn13},
        )
    return work


async def _request(adb, rid: str) -> dict:
    row = await adb.execute(
        text(
            "SELECT status, source_id, claimed_by IS NOT NULL AS claimed, active_at, closed_at"
            " FROM book_requests WHERE id = :i"
        ),
        {"i": rid},
    )
    return dict(row.mappings().one())


async def test_a_request_follows_its_book_in(client, people, adb, openlib) -> None:
    """Entered by anyone: linked when its edition arrives, and open until
    someone marks it finished; asking again is a vote."""
    rid = (await client.post("/api/requests", json={"isbn": PINK_CAKE})).json()["request"]["id"]
    work = await _book(adb, "Pink Cake", PINK_CAKE)
    await adb.execute(
        text("INSERT INTO recipes (source_id, title) VALUES (:w, 'Rhubarb Cake')"), {"w": work}
    )
    linked = await _request(adb, rid)
    assert (linked["status"], linked["source_id"]) == ("open", work)
    ann = await people("ann")
    again = (await ann.post("/api/requests", json={"isbn": PINK_CAKE})).json()
    assert (again["outcome"], again["request"]["source_id"]) == ("voted", str(work))
    ada = await people("ada", admin=True)
    done = (await ada.post(f"/api/requests/{rid}/done", json={})).json()
    assert (done["status"], done["source_id"]) == ("done", str(work))
    # Closed, so asking now is answered with the book.
    after = (await ann.post("/api/requests", json={"isbn": PINK_CAKE})).json()
    assert after == {"outcome": "in_catalog", "request": None, "source_id": str(work)}


async def test_a_request_by_title_follows_a_book_of_that_title(client, adb) -> None:
    rid = (await client.post("/api/requests", json={"title": "jerusalem"})).json()["request"]["id"]
    other = await _book(adb, "Jerusalem Cooks")
    work = await _book(adb, "Jerusalem")
    assert (await _request(adb, rid))["source_id"] == work != other


async def test_a_claim_is_kept_alive_by_work_on_its_book(people, adb, openlib) -> None:
    bo = await people("bo")
    await _make_contributor(adb, "bo")
    rid = (await bo.post("/api/requests", json={"isbn": PINK_CAKE})).json()["request"]["id"]
    await bo.post(f"/api/requests/{rid}/claim")
    await adb.execute(text("UPDATE book_requests SET active_at = now() - interval '20 days'"))
    work = await _book(adb, "Pink Cake", PINK_CAKE)
    await adb.execute(
        text("INSERT INTO recipes (source_id, title) VALUES (:w, 'Rhubarb Cake')"), {"w": work}
    )
    kept = await _request(adb, rid)
    assert (kept["status"], kept["claimed"], kept["source_id"]) == ("claimed", True, work)
    fresh = await adb.scalar(
        text("SELECT active_at > now() - interval '1 minute' FROM book_requests")
    )
    assert fresh
    # Quiet past the lapse: more work doesn't revive it, and it reads open.
    await adb.execute(text("UPDATE book_requests SET active_at = now() - interval '31 days'"))
    await adb.execute(
        text("INSERT INTO recipes (source_id, title) VALUES (:w, 'Pistachio Cake')"), {"w": work}
    )
    [shown] = (await bo.get("/api/requests")).json()["requests"]
    assert (shown["status"], shown["claimed_by"]) == ("open", None)


async def test_a_book_waiting_for_review_links_once_approved(client, adb, openlib) -> None:
    rid = (await client.post("/api/requests", json={"isbn": PINK_CAKE})).json()["request"]["id"]
    work = await _book(adb, "Pink Cake", PINK_CAKE, review="pending")
    await adb.execute(
        text("INSERT INTO recipes (source_id, title) VALUES (:w, 'Rhubarb Cake')"), {"w": work}
    )
    assert (await _request(adb, rid))["source_id"] is None
    await adb.execute(text("UPDATE sources SET review = 'published' WHERE id = :w"), {"w": work})
    after = await _request(adb, rid)
    assert (after["status"], after["source_id"]) == ("open", work)


async def test_a_private_collection_never_closes_a_request(people, adb, openlib) -> None:
    ann = await people("ann")
    rid = (await ann.post("/api/requests", json={"isbn": PINK_CAKE})).json()["request"]["id"]
    owner = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'ann'"))
    work = await adb.scalar(
        text(
            "INSERT INTO sources (title, kind, private, owner_id, acknowledged_at)"
            " VALUES ('Pink Cake', 'family', true, :o, now()) RETURNING id"
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
    left = await _request(adb, rid)
    assert (left["status"], left["source_id"]) == ("open", None)


async def test_asking_by_title_for_a_book_here_points_to_it(client, adb) -> None:
    work = await _book(adb, "Jerusalem")
    asked = (await client.post("/api/requests", json={"title": "Jerusalem"})).json()
    assert asked["request"]["source_id"] == str(work)
    await adb.execute(
        text("INSERT INTO recipes (source_id, title) VALUES (:w, 'Shakshuka')"), {"w": work}
    )
    # Still asked for, so asking again is a vote.
    again = (await client.post("/api/requests", json={"title": "jerusalem"})).json()
    assert again["outcome"] in ("voted", "already")
