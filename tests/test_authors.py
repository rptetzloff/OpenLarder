"""Author pages: the list, one author's page, and fixing an author."""

import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET role = 'admin'"))
    return client


async def _book(client, title, credits):
    """A book added by hand, then given its credits as (name, role)."""
    added = await client.post("/api/sources/manual", json={"title": title, "authors": []})
    book = (await client.get(f"/api/sources/{added.json()['id']}")).json()
    response = await client.put(
        f"/api/sources/{book['id']}",
        json={
            "title": title,
            "credits": [{"name": n, "role": r} for n, r in credits],
            "editions": [],
        },
    )
    assert response.status_code == 200, response.text
    return (await client.get(f"/api/sources/{book['id']}")).json()


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
    assert [(b["title"], b["roles"], b["credited_as"]) for b in page["sources"]] == [
        ("Jerusalem", ["author"], "Yotam Ottolenghi"),
        ("Plenty", ["author"], "Yotam Ottolenghi"),
    ]
    # Most books shared first, then by name. "Ottolenghi" on Simple is another
    # record: a different printed name is matched as a new name.
    assert [(c["name"], c["sources"]) for c in page["coauthors"]] == [
        ("Sami Tamimi", 2),
        ("Jonathan Lovekin", 1),
    ]


async def test_one_person_in_two_roles_is_one_book(admin, client) -> None:
    book = await _book(
        admin, "Camino", [("Russell Moore", "author"), ("Russell Moore", "photographer")]
    )
    page = (await client.get(f"/api/authors/{_author(book, 'Russell Moore')}")).json()
    assert [(b["title"], b["roles"]) for b in page["sources"]] == [
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
    assert [(a["name"], a["sources"]) for a in listed["authors"]] == [
        ("Jonathan Lovekin", 1),
        ("Sami Tamimi", 1),
        ("Yotam Ottolenghi", 2),
    ]
    assert listed["total"] == 3


async def test_the_list_says_what_each_is_known_for(admin, adb, client) -> None:
    plenty = await _book(admin, "Plenty", [("Yotam Ottolenghi", "author")])
    jerusalem = await _book(
        admin, "Jerusalem", [("Yotam Ottolenghi", "author"), ("Test Kitchen", "author")]
    )
    for title in ("Shakshuka", "Hummus"):
        await adb.execute(
            text("INSERT INTO recipes (source_id, title) VALUES (:s, :t)"),
            {"s": uuid.UUID(jerusalem["id"]), "t": title},
        )
    await adb.execute(
        text("INSERT INTO recipes (source_id, title) VALUES (:s, 'Salad')"),
        {"s": uuid.UUID(plenty["id"])},
    )
    await adb.execute(text("UPDATE authors SET kind = 'organisation' WHERE name = 'Test Kitchen'"))
    listed = {a["name"]: a for a in (await client.get("/api/authors")).json()["authors"]}
    yotam = listed["Yotam Ottolenghi"]
    assert (yotam["kind"], yotam["sources"], yotam["recipes"]) == ("person", 2, 3)
    assert yotam["known_for"] == {"id": jerusalem["id"], "title": "Jerusalem"}
    assert (listed["Test Kitchen"]["kind"], listed["Test Kitchen"]["recipes"]) == (
        "organisation",
        2,
    )
    names = lambda r: [a["name"] for a in r.json()["authors"]]  # noqa: E731
    most = await client.get("/api/authors", params={"sort": "recipes"})
    assert names(most) == ["Yotam Ottolenghi", "Test Kitchen"]
    people = await client.get("/api/authors", params={"kind": "person"})
    assert names(people) == ["Yotam Ottolenghi"]
    assert people.json()["total"] == 1


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
    assert response.json() == {"id": atk, "name": "America's Test Kitchen", "sources": 1}
    page = (await client.get(f"/api/authors/{atk}")).json()
    assert (page["name"], page["kind"]) == ("America's Test Kitchen", "organisation")
    # The book still prints what it printed.
    shown = (await client.get(f"/api/sources/{book['id']}")).json()
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
    await adb.execute(text("UPDATE users SET role = 'user'"))
    assert (
        await admin.patch(f"/api/authors/{yotam}", json={"name": "X", "kind": "person"})
    ).status_code == 403
    assert (
        await admin.post(f"/api/authors/{yotam}/links", json={"url": "https://b.example"})
    ).status_code == 403
    assert (await admin.delete(f"/api/authors/{yotam}/links/{link['id']}")).status_code == 403


# Two records of one person


async def _two_mclagans(admin, adb):
    """Bones credits one record and Fat another, as Open Library had it."""
    bones = await _book(admin, "Bones", [("Jennifer McLagan", "author")])
    fat = await _book(admin, "Fat", [])
    other = await adb.scalar(
        text(
            "INSERT INTO authors (name, name_key, open_library_author_id)"
            " VALUES ('Jennifer Mclagan', 'jennifer mclagan', 'OL9A') RETURNING id"
        )
    )
    await adb.execute(
        text(
            "INSERT INTO source_credits (source_id, author_id, position, credited_as)"
            " VALUES (:s, :a, 1, 'Jennifer Mclagan')"
        ),
        {"s": fat["id"], "a": other},
    )
    return _author(bones, "Jennifer McLagan"), str(other), bones, fat


async def test_an_author_page_lists_the_same_name(admin, adb, client) -> None:
    mine, theirs, _, _ = await _two_mclagans(admin, adb)
    page = (await client.get(f"/api/authors/{mine}")).json()
    assert page["same_name"] == [{"id": theirs, "name": "Jennifer Mclagan", "sources": 1}]


async def test_merging_moves_sources_and_keeps_printed_names(admin, adb, client) -> None:
    mine, theirs, bones, fat = await _two_mclagans(admin, adb)
    response = await admin.post(f"/api/authors/{theirs}/merge", json={"into": mine})
    assert response.json() == {"id": mine, "name": "Jennifer McLagan", "sources": 2}
    assert (await client.get(f"/api/authors/{theirs}")).status_code == 404
    page = (await client.get(f"/api/authors/{mine}")).json()
    assert [s["title"] for s in page["sources"]] == ["Bones", "Fat"]
    assert page["same_name"] == []
    shown = (await client.get(f"/api/sources/{fat['id']}")).json()
    assert [(c["author_id"], c["credited_as"]) for c in shown["credits"]] == [
        (mine, "Jennifer Mclagan")
    ]
    # Open Library's record came along, since the one kept had none.
    ol = await adb.scalar(
        text("SELECT open_library_author_id FROM authors WHERE id = :a"), {"a": mine}
    )
    assert ol == "OL9A"


async def test_merging_keeps_one_credit_and_one_of_each_link(admin, adb, client) -> None:
    mine, theirs, bones, _ = await _two_mclagans(admin, adb)
    await adb.execute(
        text(
            "INSERT INTO source_credits (source_id, author_id, position, credited_as, role)"
            " VALUES (:s, :a, 2, 'J. McLagan', 'author'), (:s, :a, 3, 'J. McLagan', 'photographer')"
        ),
        {"s": bones["id"], "a": theirs},
    )
    for author, url in (
        (mine, "https://jennifermclagan.com"),
        (theirs, "https://jennifermclagan.com"),
        (theirs, "https://instagram.com/jm"),
    ):
        await admin.post(f"/api/authors/{author}/links", json={"url": url})
    await admin.post(f"/api/authors/{theirs}/merge", json={"into": mine})
    shown = (await client.get(f"/api/sources/{bones['id']}")).json()
    assert [(c["credited_as"], c["role"]) for c in shown["credits"]] == [
        ("Jennifer McLagan", "author"),
        ("J. McLagan", "photographer"),
    ]
    links = (await client.get(f"/api/authors/{mine}")).json()["links"]
    assert sorted(x["url"] for x in links) == [
        "https://instagram.com/jm",
        "https://jennifermclagan.com",
    ]


async def test_when_both_have_an_outside_record_the_kept_ones_stays(admin, adb) -> None:
    mine, theirs, _, _ = await _two_mclagans(admin, adb)
    await adb.execute(
        text(
            "UPDATE authors SET open_library_author_id = 'OL1A', wikidata_id = 'Q5' WHERE id = :a"
        ),
        {"a": mine},
    )
    await adb.execute(text("UPDATE authors SET wikidata_id = 'Q7' WHERE id = :a"), {"a": theirs})
    assert (
        await admin.post(f"/api/authors/{theirs}/merge", json={"into": mine})
    ).status_code == 200
    row = (
        await adb.execute(
            text("SELECT open_library_author_id, wikidata_id FROM authors WHERE id = :a"),
            {"a": mine},
        )
    ).one()
    assert tuple(row) == ("OL1A", "Q5")


async def test_a_merge_needs_two_authors_and_an_admin(admin, adb) -> None:
    mine, theirs, _, _ = await _two_mclagans(admin, adb)
    assert (await admin.post(f"/api/authors/{mine}/merge", json={"into": mine})).status_code == 422
    missing = await admin.post(f"/api/authors/{mine}/merge", json={"into": str(uuid.uuid4())})
    assert missing.status_code == 404
    await adb.execute(text("UPDATE users SET role = 'user'"))
    assert (
        await admin.post(f"/api/authors/{theirs}/merge", json={"into": mine})
    ).status_code == 403
