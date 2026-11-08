"""Editing a book: title, subtitle, credits and editions."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET is_admin = true"))
    return client


async def _book(client, title="Heritage", authors=("Moore, Russell (Chef)",), year=2020):
    response = await client.post(
        "/api/sources/manual", json={"title": title, "authors": list(authors), "year": year}
    )
    assert response.status_code == 200, response.text
    return (await client.get(f"/api/sources/{response.json()['id']}")).json()


def _same(book, **changes):
    """The book as the form would send it back, with changes."""
    body = {
        "title": book["title"],
        "subtitle": book["subtitle"],
        "credits": [
            {"author_id": c["author_id"], "name": c["credited_as"], "role": c["role"]}
            for c in book["credits"]
        ],
        "editions": [
            {
                "id": e["id"],
                "title": e["title"],
                "publisher": e["publisher"],
                "published_year": e["published_year"],
            }
            for e in book["editions"]
        ],
    }
    return {**body, **changes}


async def _edit(client, book, **changes):
    return await client.put(f"/api/sources/{book['id']}", json=_same(book, **changes))


async def _names(adb):
    return (await adb.scalars(text("SELECT name FROM authors ORDER BY name"))).all()


async def test_title_and_subtitle_change(admin, client) -> None:
    book = await _book(admin)
    response = await _edit(admin, book, title="  The Heritage  Cookbook ", subtitle="Recipes")
    assert response.status_code == 200, response.text
    shown = (await client.get(f"/api/sources/{book['id']}")).json()
    assert (shown["title"], shown["subtitle"]) == ("The Heritage Cookbook", "Recipes")
    await _edit(admin, shown, subtitle="  ")
    assert (await client.get(f"/api/sources/{book['id']}")).json()["subtitle"] is None


async def test_a_book_needs_a_title(admin) -> None:
    book = await _book(admin)
    response = await _edit(admin, book, title="   ")
    assert response.status_code == 422


async def test_renaming_a_credit_fixes_the_author_too(admin, adb, client) -> None:
    book = await _book(admin)
    author = book["credits"][0]["author_id"]
    credits = [{"author_id": author, "name": "Russell Moore", "role": "author"}]
    assert (await _edit(admin, book, credits=credits)).status_code == 200
    shown = (await client.get(f"/api/sources/{book['id']}")).json()
    assert [(c["author_id"], c["credited_as"]) for c in shown["credits"]] == [
        (author, "Russell Moore")
    ]
    assert await _names(adb) == ["Russell Moore"]


async def test_an_author_with_other_books_keeps_their_name(admin, adb) -> None:
    book = await _book(admin, authors=["Sarah Ballantyne"])
    await _book(admin, title="Paleo Approach", authors=["Sarah Ballantyne"])
    author = book["credits"][0]["author_id"]
    credits = [{"author_id": author, "name": "Sarah Ballantyne, PhD", "role": "author"}]
    await _edit(admin, book, credits=credits)
    # Printed differently on this cover; the person is the same.
    assert await _names(adb) == ["Sarah Ballantyne"]


async def test_an_open_library_author_keeps_their_name(admin, adb) -> None:
    book = await _book(admin, authors=["Yotam Ottolenghi"])
    author = book["credits"][0]["author_id"]
    await adb.execute(
        text("UPDATE authors SET open_library_author_id = 'OL1A' WHERE id = :a"), {"a": author}
    )
    credits = [{"author_id": author, "name": "Ottolenghi", "role": "author"}]
    await _edit(admin, book, credits=credits)
    assert await _names(adb) == ["Yotam Ottolenghi"]


async def test_credits_are_added_reordered_and_removed(admin, adb, client) -> None:
    other = await _book(admin, title="Other", authors=["Jonathan Lovekin"])
    book = await _book(admin, authors=["Yotam Ottolenghi", "Someone Wrong"])
    yotam, wrong = [c["author_id"] for c in book["credits"]]
    credits = [
        {"name": "Jonathan Lovekin", "role": "photographer"},
        {"author_id": yotam, "name": "Yotam Ottolenghi", "role": "author"},
    ]
    assert (await _edit(admin, book, credits=credits)).status_code == 200
    shown = (await client.get(f"/api/sources/{book['id']}")).json()
    assert [(c["credited_as"], c["role"]) for c in shown["credits"]] == [
        ("Jonathan Lovekin", "photographer"),
        ("Yotam Ottolenghi", "author"),
    ]
    # The new name is the author the other book already credits.
    assert shown["credits"][0]["author_id"] == other["credits"][0]["author_id"]
    # Someone Wrong is credited nowhere now, and had no outside record.
    assert await _names(adb) == ["Jonathan Lovekin", "Yotam Ottolenghi"]
    assert wrong not in [c["author_id"] for c in shown["credits"]]


async def test_a_removed_author_with_an_outside_record_stays(admin, adb) -> None:
    book = await _book(admin, authors=["Yotam Ottolenghi"])
    await adb.execute(text("UPDATE authors SET wikidata_id = 'Q123'"))
    await _edit(admin, book, credits=[])
    assert await _names(adb) == ["Yotam Ottolenghi"]


@pytest.mark.parametrize(
    "credit, reason",
    [
        ({"name": "  ", "role": "author"}, "name"),
        ({"name": "X", "role": "chef"}, "role"),
        ({"author_id": str(uuid.uuid4()), "name": "X", "role": "author"}, "author"),
    ],
)
async def test_a_bad_credit_is_refused(admin, adb, client, credit, reason) -> None:
    book = await _book(admin)
    response = await _edit(admin, book, credits=[credit])
    assert response.status_code == 422
    assert reason in response.json()["detail"]
    shown = (await client.get(f"/api/sources/{book['id']}")).json()
    assert [c["credited_as"] for c in shown["credits"]] == ["Moore, Russell (Chef)"]


async def test_the_same_person_twice_in_one_role_is_refused(admin) -> None:
    book = await _book(admin)
    author = book["credits"][0]["author_id"]
    credits = [
        {"author_id": author, "name": "Russell Moore", "role": "author"},
        {"name": "Jonathan Lovekin", "role": "photographer"},
        {"name": "jonathan lovekin", "role": "photographer"},
    ]
    response = await _edit(admin, book, credits=credits)
    assert response.status_code == 422
    assert "twice" in response.json()["detail"]


async def test_one_person_in_two_roles_is_fine(admin) -> None:
    book = await _book(admin)
    author = book["credits"][0]["author_id"]
    credits = [
        {"author_id": author, "name": "Russell Moore", "role": "author"},
        {"author_id": author, "name": "Russell Moore", "role": "photographer"},
    ]
    assert (await _edit(admin, book, credits=credits)).status_code == 200


async def test_an_edition_changes(admin, client) -> None:
    book = await _book(admin)
    edition = book["editions"][0]
    editions = [
        {
            "id": edition["id"],
            "title": " Heritage (UK) ",
            "publisher": " Ten Speed ",
            "published_year": 2021,
        }
    ]
    assert (await _edit(admin, book, editions=editions)).status_code == 200
    shown = (await client.get(f"/api/sources/{book['id']}")).json()["editions"][0]
    assert (shown["title"], shown["publisher"], shown["published_year"]) == (
        "Heritage (UK)",
        "Ten Speed",
        2021,
    )
    # The book's own title, or nothing, means no title of its own.
    for same in ("Heritage", ""):
        editions[0]["title"] = same
        await _edit(admin, book, editions=editions)
        shown = (await client.get(f"/api/sources/{book['id']}")).json()["editions"][0]
        assert shown["title"] is None


@pytest.mark.parametrize("year", [1399, 2201])
async def test_an_impossible_year_is_refused(admin, year) -> None:
    book = await _book(admin)
    editions = [{"id": book["editions"][0]["id"], "published_year": year}]
    assert (await _edit(admin, book, editions=editions)).status_code == 422


async def test_another_books_edition_is_refused(admin) -> None:
    book = await _book(admin)
    other = await _book(admin, title="Other", authors=[])
    editions = [{"id": other["editions"][0]["id"], "publisher": "Mine now"}]
    response = await _edit(admin, book, editions=editions)
    assert response.status_code == 422


async def test_only_admins_edit_books(admin, adb) -> None:
    book = await _book(admin)
    await adb.execute(text("UPDATE users SET is_admin = false"))
    assert (await _edit(admin, book, title="Mine")).status_code == 403


async def test_an_unknown_book_is_a_404(admin) -> None:
    book = await _book(admin)
    response = await admin.put(f"/api/sources/{uuid.uuid4()}", json=_same(book))
    assert response.status_code == 404


async def test_a_new_name_is_not_matched_to_an_open_library_author(admin, adb) -> None:
    """As when a book is added by hand: same name, no shared record, not
    known to be the same person."""
    first = await _book(admin, title="Plenty", authors=["Yotam Ottolenghi"])
    await adb.execute(text("UPDATE authors SET open_library_author_id = 'OL1A'"))
    book = await _book(admin, title="Other", authors=[])
    await _edit(admin, book, credits=[{"name": "Yotam Ottolenghi", "role": "author"}])
    ids = (await adb.scalars(text("SELECT id FROM authors ORDER BY open_library_author_id"))).all()
    assert len(ids) == 2
    assert str(ids[0]) == first["credits"][0]["author_id"]


# Finding a book by name (the list's q and limit)


async def test_books_are_found_by_title_subtitle_or_credit(admin, client) -> None:
    await _book(admin, title="Plenty", authors=["Yotam Ottolenghi", "Jonathan Lovekin"])
    camino = await _book(admin, title="This Is Camino", authors=["Russell Moore"])
    await _edit(admin, camino, subtitle="Recipes from the Oakland restaurant")
    await _book(admin, title="100% Rye", authors=[])
    titles = lambda r: [b["title"] for b in r.json()]  # noqa: E731
    assert titles(await client.get("/api/sources", params={"q": "PLENTY"})) == ["Plenty"]
    assert titles(await client.get("/api/sources", params={"q": "lovekin"})) == ["Plenty"]
    assert titles(await client.get("/api/sources", params={"q": "oakland"})) == ["This Is Camino"]
    # Every word, wherever it is.
    assert titles(await client.get("/api/sources", params={"q": "camino moore"})) == [
        "This Is Camino"
    ]
    assert titles(await client.get("/api/sources", params={"q": "camino lovekin"})) == []
    assert titles(await client.get("/api/sources", params={"q": "%"})) == ["100% Rye"]
    assert titles(await client.get("/api/sources", params={"q": "  "})) == [
        "100% Rye",
        "Plenty",
        "This Is Camino",
    ]


async def test_a_picker_asks_for_a_few(admin, client) -> None:
    for title in ("Bread A", "Bread B", "Bread C"):
        await _book(admin, title=title, authors=[])
    found = await client.get("/api/sources", params={"q": "bread", "limit": 2})
    assert [b["title"] for b in found.json()] == ["Bread A", "Bread B"]
    assert (await client.get("/api/sources", params={"limit": 51})).status_code == 422
