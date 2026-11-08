"""Author pages: the list, one author's page, and fixing an author."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET is_admin = true"))
    return client


async def _book(client, title, credits):
    """A book added by hand, then given its credits as (name, role)."""
    added = await client.post("/api/books/manual", json={"title": title, "authors": []})
    book = (await client.get(f"/api/books/{added.json()['id']}")).json()
    response = await client.put(
        f"/api/books/{book['id']}",
        json={
            "title": title,
            "credits": [{"name": n, "role": r} for n, r in credits],
            "editions": [],
        },
    )
    assert response.status_code == 200, response.text
    return (await client.get(f"/api/books/{book['id']}")).json()


def _author(book, name):
    return next(c["author_id"] for c in book["credits"] if c["credited_as"] == name)


async def test_an_author_page_lists_books_and_coauthors(admin, client) -> None:
    plenty = await _book(
        admin,
        "Plenty",
        [
            ("Yotam Ottolenghi", "author"),
            ("Sami Tamimi", "contributor"),
            # Two roles on one book is still one book together.
            ("Jonathan Lovekin", "photographer"),
            ("Jonathan Lovekin", "contributor"),
        ],
    )
    await _book(admin, "Jerusalem", [("Yotam Ottolenghi", "author"), ("Sami Tamimi", "author")])
    await _book(admin, "Simple", [("Ottolenghi", "author")])
    await _book(admin, "Falastin", [("Sami Tamimi", "author")])
    yotam = _author(plenty, "Yotam Ottolenghi")
    page = (await client.get(f"/api/authors/{yotam}")).json()
    assert (page["name"], page["kind"], page["open_library_url"]) == (
        "Yotam Ottolenghi",
        "person",
        None,
    )
    assert [(b["title"], b["roles"], b["credited_as"]) for b in page["books"]] == [
        ("Jerusalem", ["author"], "Yotam Ottolenghi"),
        ("Plenty", ["author"], "Yotam Ottolenghi"),
    ]
    # Most books shared first, then by name. "Ottolenghi" on Simple is another
    # record: a different printed name is matched as a new name.
    assert [(c["name"], c["books"]) for c in page["coauthors"]] == [
        ("Sami Tamimi", 2),
        ("Jonathan Lovekin", 1),
    ]


async def test_one_person_in_two_roles_is_one_book(admin, client) -> None:
    book = await _book(
        admin, "Camino", [("Russell Moore", "author"), ("Russell Moore", "photographer")]
    )
    page = (await client.get(f"/api/authors/{_author(book, 'Russell Moore')}")).json()
    assert [(b["title"], b["roles"]) for b in page["books"]] == [
        ("Camino", ["author", "photographer"])
    ]
    assert page["coauthors"] == []


async def test_an_open_library_author_links_there(admin, adb, client) -> None:
    book = await _book(admin, "Plenty", [("Yotam Ottolenghi", "author")])
    yotam = _author(book, "Yotam Ottolenghi")
    await adb.execute(
        text("UPDATE authors SET open_library_author_id = 'OL6591369A' WHERE id = :a"),
        {"a": yotam},
    )
    page = (await client.get(f"/api/authors/{yotam}")).json()
    assert page["open_library_url"] == "https://openlibrary.org/authors/OL6591369A"


async def test_an_unknown_author_is_a_404(client) -> None:
    assert (await client.get(f"/api/authors/{uuid.uuid4()}")).status_code == 404


# The list


async def test_the_list_is_by_name_with_book_counts(admin, client) -> None:
    await _book(
        admin,
        "Plenty",
        [
            ("Yotam Ottolenghi", "author"),
            ("Jonathan Lovekin", "photographer"),
            ("Jonathan Lovekin", "contributor"),
        ],
    )
    await _book(admin, "Jerusalem", [("Yotam Ottolenghi", "author"), ("Sami Tamimi", "author")])
    listed = (await client.get("/api/authors")).json()
    assert [(a["name"], a["books"]) for a in listed["authors"]] == [
        ("Jonathan Lovekin", 1),
        ("Sami Tamimi", 1),
        ("Yotam Ottolenghi", 2),
    ]
    assert listed["total"] == 3


async def test_the_list_narrows_by_name_or_printed_name(admin, adb, client) -> None:
    book = await _book(
        admin, "Camino", [("Russell Moore", "author"), ("Allison Hopelain", "author")]
    )
    await adb.execute(
        text("UPDATE authors SET name = 'Moore, R. (Chef)' WHERE id = :a"),
        {"a": _author(book, "Russell Moore")},
    )
    names = lambda r: [a["name"] for a in r.json()["authors"]]  # noqa: E731
    # Found by the record's name, and by the name the book prints.
    assert names(await client.get("/api/authors", params={"q": "chef"})) == ["Moore, R. (Chef)"]
    assert names(await client.get("/api/authors", params={"q": "russell moore"})) == [
        "Moore, R. (Chef)"
    ]
    assert names(await client.get("/api/authors", params={"q": "hopelain moore"})) == []


async def test_the_list_comes_in_pages(admin, client, monkeypatch) -> None:
    monkeypatch.setattr("openlarder.routers.authors.PAGE", 2)
    await _book(admin, "Book", [(f"Author {n}", "author") for n in range(5)])
    rest = (await client.get("/api/authors", params={"offset": 4})).json()
    assert ([a["name"] for a in rest["authors"]], rest["total"]) == (["Author 4"], 5)


# Fixing an author


async def test_an_admin_fixes_the_name_and_kind(admin, client) -> None:
    book = await _book(admin, "Gluten Free", [("America's Test Kitchen (Firm)", "author")])
    atk = _author(book, "America's Test Kitchen (Firm)")
    response = await admin.patch(
        f"/api/authors/{atk}", json={"name": " America's  Test Kitchen ", "kind": "organisation"}
    )
    assert response.json() == {"id": atk, "name": "America's Test Kitchen", "books": 1}
    page = (await client.get(f"/api/authors/{atk}")).json()
    assert (page["name"], page["kind"]) == ("America's Test Kitchen", "organisation")
    # The book still prints what it printed.
    shown = (await client.get(f"/api/books/{book['id']}")).json()
    assert shown["credits"][0]["credited_as"] == "America's Test Kitchen (Firm)"


@pytest.mark.parametrize("body", [{"name": "  ", "kind": "person"}, {"name": "X", "kind": "robot"}])
async def test_a_bad_fix_is_refused(admin, client, body) -> None:
    book = await _book(admin, "Plenty", [("Yotam Ottolenghi", "author")])
    response = await admin.patch(f"/api/authors/{_author(book, 'Yotam Ottolenghi')}", json=body)
    assert response.status_code == 422


async def test_links_are_added_and_removed(admin, client) -> None:
    book = await _book(admin, "Plenty", [("Yotam Ottolenghi", "author")])
    yotam = _author(book, "Yotam Ottolenghi")
    site = await admin.post(
        f"/api/authors/{yotam}/links",
        json={"url": " https://ottolenghi.co.uk ", "label": " Books and recipes "},
    )
    assert site.status_code == 201
    assert site.json()["url"] == "https://ottolenghi.co.uk"
    assert site.json()["label"] == "Books and recipes"
    again = await admin.post(
        f"/api/authors/{yotam}/links", json={"url": "https://ottolenghi.co.uk"}
    )
    assert again.status_code == 409
    insta = await admin.post(
        f"/api/authors/{yotam}/links", json={"url": "http://instagram.com/ottolenghi"}
    )
    page = (await client.get(f"/api/authors/{yotam}")).json()
    # By label, or the address when there's none.
    assert [(x["url"], x["label"]) for x in page["links"]] == [
        ("https://ottolenghi.co.uk", "Books and recipes"),
        ("http://instagram.com/ottolenghi", None),
    ]
    other = await _book(admin, "Falastin", [("Sami Tamimi", "author")])
    sami = _author(other, "Sami Tamimi")
    wrong = await admin.delete(f"/api/authors/{sami}/links/{insta.json()['id']}")
    assert wrong.status_code == 404
    gone = await admin.delete(f"/api/authors/{yotam}/links/{insta.json()['id']}")
    assert gone.status_code == 204
    assert len((await client.get(f"/api/authors/{yotam}")).json()["links"]) == 1


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "ftp://example.com", "ottolenghi.co.uk", "https://", "  "]
)
async def test_a_link_must_be_a_web_address(admin, url) -> None:
    book = await _book(admin, "Plenty", [("Yotam Ottolenghi", "author")])
    yotam = _author(book, "Yotam Ottolenghi")
    response = await admin.post(f"/api/authors/{yotam}/links", json={"url": url})
    assert response.status_code == 422


async def test_only_admins_fix_authors(admin, adb) -> None:
    book = await _book(admin, "Plenty", [("Yotam Ottolenghi", "author")])
    yotam = _author(book, "Yotam Ottolenghi")
    link = (
        await admin.post(f"/api/authors/{yotam}/links", json={"url": "https://a.example"})
    ).json()
    await adb.execute(text("UPDATE users SET is_admin = false"))
    assert (
        await admin.patch(f"/api/authors/{yotam}", json={"name": "X", "kind": "person"})
    ).status_code == 403
    assert (
        await admin.post(f"/api/authors/{yotam}/links", json={"url": "https://b.example"})
    ).status_code == 403
    assert (await admin.delete(f"/api/authors/{yotam}/links/{link['id']}")).status_code == 403
