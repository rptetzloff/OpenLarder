"""Linking a book already here to Open Library (issue #32).

The worked example is the issue's: The Heritage Cookbook, added from the
household index without an Open Library match. Open Library now has that
printing (OL62720971M, ISBN 978-0-578-52428-3) under work OL21362065W,
beside the Victory Belt printing (OL28936410M). Their records are saved
in tests/data/openlibrary.
"""

import copy

import pytest
from sqlalchemy import text

from fake_broker import _sign_in, make_admins
from fake_openlibrary import _real
from openlarder import linking, openlibrary

HERITAGE = "9780578524283"
VICTORY_BELT = "9781628603125"
WORK = "OL21362065W"
CRANDALL = "OL7594453A"


@pytest.fixture
def heritage(openlib):
    openlib.records.update(
        {
            f"/isbn/{HERITAGE}.json": _real(f"isbn_{HERITAGE}"),
            "/books/OL62720971M.json": _real(f"isbn_{HERITAGE}"),
            "/books/OL28936410M.json": _real("books_OL28936410M"),
            f"/isbn/{VICTORY_BELT}.json": _real("books_OL28936410M"),
            f"/works/{WORK}.json": _real(f"works_{WORK}"),
            f"/authors/{CRANDALL}.json": _real(f"authors_{CRANDALL}"),
        }
    )
    return openlib


@pytest.fixture
async def admin(client, broker, adb, heritage):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


async def _manual(client, title="The Heritage Cookbook", authors=("Russ Crandall",), **extra):
    body = {"title": title, "authors": list(authors), "isbn": HERITAGE, **extra}
    response = await client.post("/api/sources/manual", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _preview(client, source_id, reference):
    return await client.post(
        f"/api/sources/{source_id}/open-library/preview", json={"reference": reference}
    )


async def _link(client, source_id, reference):
    return await client.post(
        f"/api/sources/{source_id}/open-library", json={"reference": reference}
    )


async def _row(adb, sql, **params):
    return (await adb.execute(text(sql), params)).one()


# What can be typed


@pytest.mark.parametrize(
    "raw, parsed",
    [
        ("978-0-578-52428-3", ("isbn", HERITAGE)),
        ("0578524287", ("isbn", HERITAGE)),
        ("https://openlibrary.org/books/OL62720971M/Heritage_Cookbook", ("edition", "OL62720971M")),
        ("https://openlibrary.org/works/OL21362065W/Heritage_Cookbook", ("work", WORK)),
        ("ol21362065w", ("work", WORK)),
        (" OL28936410M ", ("edition", "OL28936410M")),
    ],
)
def test_references_name_an_isbn_edition_or_work(raw, parsed) -> None:
    assert openlibrary.parse_reference(raw) == parsed


@pytest.mark.parametrize("raw", ["", "heritage cookbook", "OL123A", "https://openlibrary.org/"])
def test_anything_else_is_refused(raw) -> None:
    with pytest.raises(openlibrary.BadReference):
        openlibrary.parse_reference(raw)


@pytest.mark.parametrize(
    "ours, theirs",
    [
        ("Moore, Russell (Chef)", "Russell Moore"),
        ("America's Test Kitchen (Firm)", "America's Test Kitchen"),
        ("Crandall, Russ", "Russ Crandall"),
        ("José Andrés", "Jose Andres"),
    ],
)
def test_names_match_however_they_are_written(ours, theirs) -> None:
    assert linking.name_key(ours) == linking.name_key(theirs)


def test_different_names_do_not_match() -> None:
    assert linking.name_key("Russ Crandall") != linking.name_key("Russell Moore")


# The worked example


async def test_the_preview_shows_what_linking_would_do_and_writes_nothing(admin, adb) -> None:
    book = await _manual(admin)
    response = await _preview(admin, book, HERITAGE)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["problem"] is None
    assert preview["title"] == "Heritage Cookbook"
    assert preview["open_library_url"] == f"https://openlibrary.org/works/{WORK}"
    assert preview["edition"]["step"] == "fill"
    assert preview["edition"]["fills_isbn13"] == HERITAGE
    assert preview["edition"]["publisher"] == "Self-Published"
    assert preview["authors"] == [
        {
            "name": "Russ Crandall",
            "open_library_url": f"https://openlibrary.org/authors/{CRANDALL}",
            "outcome": "link",
            "credited_as": "Russ Crandall",
        }
    ]
    source_id = await adb.scalar(text("SELECT open_library_work_id FROM sources"))
    assert source_id is None


async def test_linking_fills_in_the_edition_and_ties_the_author(admin, adb) -> None:
    book = await _manual(admin, year=2019)
    response = await _link(admin, book, HERITAGE)
    assert response.status_code == 200, response.text

    title, source_id = await _row(adb, "SELECT title, open_library_work_id FROM sources")
    # Linking doesn't rewrite the book's own title with Open Library's.
    assert (title, source_id) == ("The Heritage Cookbook", WORK)
    editions = (
        await adb.execute(
            text("SELECT isbn13, publisher, published_year, open_library_edition_id FROM editions")
        )
    ).all()
    assert [tuple(e) for e in editions] == [(HERITAGE, "Self-Published", 2019, "OL62720971M")]
    credit, name, author_id = await _row(
        adb,
        "SELECT c.credited_as, a.name, a.open_library_author_id"
        " FROM source_credits c JOIN authors a ON a.id = c.author_id",
    )
    assert (credit, name, author_id) == ("Russ Crandall", "Russ Crandall", CRANDALL)

    shown = (await admin.get(f"/api/sources/{book}")).json()
    assert shown["open_library_url"] == f"https://openlibrary.org/works/{WORK}"


async def test_an_edition_keeps_what_it_already_says(admin, adb) -> None:
    book = await _manual(admin, year=2020)
    await adb.execute(text("UPDATE editions SET publisher = 'Russ Crandall'"))
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    publisher, year = await _row(adb, "SELECT publisher, published_year FROM editions")
    assert (publisher, year) == ("Russ Crandall", 2020)


async def test_the_other_printing_joins_as_another_edition(admin, adb) -> None:
    book = await _manual(admin)
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    preview = (await _preview(admin, book, "https://openlibrary.org/books/OL28936410M")).json()
    assert (preview["problem"], preview["edition"]["step"]) == (None, "add")
    assert preview["authors"][0]["outcome"] == "linked"
    assert (await _link(admin, book, "OL28936410M")).status_code == 200

    isbns = (await adb.scalars(text("SELECT isbn13 FROM editions ORDER BY isbn13"))).all()
    assert isbns == [HERITAGE, VICTORY_BELT]
    assert await adb.scalar(text("SELECT count(*) FROM sources")) == 1
    assert await adb.scalar(text("SELECT count(*) FROM source_credits")) == 1


async def test_once_linked_the_add_box_joins_the_book_too(admin, adb) -> None:
    """The problem the issue describes: adding the Victory Belt ISBN made a second book."""
    book = await _manual(admin)
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    response = await admin.post("/api/sources", json={"isbn": VICTORY_BELT})
    assert response.status_code == 201
    assert response.json()["id"] == book
    assert await adb.scalar(text("SELECT count(*) FROM sources")) == 1


async def test_recipes_and_their_pages_are_left_alone(admin, adb) -> None:
    book = await _manual(admin)
    edition = await adb.scalar(text("SELECT id FROM editions"))
    response = await admin.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Ajiaco",
            "editions": [{"edition_id": str(edition), "page": "634"}],
            "ingredients": ["potato"],
        },
    )
    assert response.status_code == 201, response.text
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    page = await adb.scalar(text("SELECT page FROM recipe_locations"))
    assert page == "634"


async def test_a_work_link_sets_the_work_without_adding_an_edition(admin, adb) -> None:
    book = await _manual(admin)
    preview = (await _preview(admin, book, f"https://openlibrary.org/works/{WORK}")).json()
    assert preview["edition"] is None
    assert (await _link(admin, book, WORK)).status_code == 200
    assert await adb.scalar(text("SELECT open_library_work_id FROM sources")) == WORK
    assert await adb.scalar(text("SELECT open_library_edition_id FROM editions")) is None


# Authors


async def test_a_book_with_no_authors_is_given_open_librarys(admin, adb) -> None:
    book = await _manual(admin, authors=())
    preview = (await _preview(admin, book, HERITAGE)).json()
    assert preview["authors"][0]["outcome"] == "add"
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    row = await _row(
        adb,
        "SELECT c.credited_as, c.position, a.open_library_author_id"
        " FROM source_credits c JOIN authors a ON a.id = c.author_id",
    )
    assert tuple(row) == ("Russ Crandall", 1, CRANDALL)


async def test_an_author_written_backwards_still_matches(admin, adb) -> None:
    book = await _manual(admin, authors=("Crandall, Russ (Author)",))
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    credit, author_id = await _row(
        adb,
        "SELECT c.credited_as, a.open_library_author_id"
        " FROM source_credits c JOIN authors a ON a.id = c.author_id",
    )
    # Tied to Open Library's record, still credited as the book has it.
    assert (credit, author_id) == ("Crandall, Russ (Author)", CRANDALL)


async def test_an_author_open_library_has_that_the_book_does_not_is_left_off(admin, adb) -> None:
    book = await _manual(admin, authors=("Someone Else",))
    preview = (await _preview(admin, book, HERITAGE)).json()
    assert [a["outcome"] for a in preview["authors"]] == ["unmatched"]
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    names = (
        await adb.execute(
            text(
                "SELECT c.credited_as, a.open_library_author_id"
                " FROM source_credits c JOIN authors a ON a.id = c.author_id"
            )
        )
    ).all()
    assert [tuple(n) for n in names] == [("Someone Else", None)]
    assert await adb.scalar(text("SELECT count(*) FROM authors")) == 1


async def test_a_typed_name_finds_the_open_library_author_already_here(admin, adb) -> None:
    """Typed "Crandall, Russ" is Open Library's Russ Crandall from the start
    (books.author_named); there's no second record for linking to merge.
    *Reversed 2026-11-08: Open Library's authors were left out of matching,
    which made a second Katarina Cermelj.*"""
    await adb.execute(
        text(
            "INSERT INTO authors (name, name_key, open_library_author_id)"
            " VALUES ('Russ Crandall', 'russ crandall', :id)"
        ),
        {"id": CRANDALL},
    )
    book = await _manual(admin, authors=("Crandall, Russ",))
    credited = await adb.scalar(
        text(
            "SELECT a.open_library_author_id"
            " FROM source_credits c JOIN authors a ON a.id = c.author_id"
        )
    )
    assert credited == CRANDALL
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    assert await adb.scalar(text("SELECT count(*) FROM authors")) == 1


async def _plain_crandall(adb, *books) -> None:
    """A record for him made before typed names matched Open Library's."""
    plain = await adb.scalar(
        text(
            "INSERT INTO authors (name, name_key) VALUES ('Russ Crandall', 'russ crandall')"
            " RETURNING id"
        )
    )
    for book in books:
        await adb.execute(
            text(
                "INSERT INTO source_credits (source_id, author_id, position, credited_as)"
                " VALUES (:b, :a, 1, 'Crandall, Russ')"
            ),
            {"b": book, "a": plain},
        )
    return plain


async def test_an_author_already_here_from_another_book_is_merged(admin, adb) -> None:
    await adb.execute(
        text(
            "INSERT INTO authors (name, name_key, open_library_author_id)"
            " VALUES ('Russ Crandall', 'russ crandall', :id)"
        ),
        {"id": CRANDALL},
    )
    book = await _manual(admin, authors=())
    plain = await _plain_crandall(adb, book)
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    tied = await adb.scalar(
        text(
            "SELECT a.open_library_author_id"
            " FROM source_credits c JOIN authors a ON a.id = c.author_id"
        )
    )
    assert tied == CRANDALL
    # The record made for this book alone is gone; only Open Library's remains.
    assert await adb.scalar(text("SELECT count(*) FROM authors WHERE id = :id"), {"id": plain}) == 0
    assert await adb.scalar(text("SELECT count(*) FROM authors")) == 1


async def test_an_author_tied_to_another_record_is_not_retied(admin, adb) -> None:
    book = await _manual(admin)
    await adb.execute(text("UPDATE authors SET open_library_author_id = 'OL1A'"))
    preview = (await _preview(admin, book, HERITAGE)).json()
    assert [a["outcome"] for a in preview["authors"]] == ["unmatched"]
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    assert await adb.scalar(text("SELECT open_library_author_id FROM authors")) == "OL1A"


async def test_a_shared_author_record_is_kept_when_merged(admin, adb) -> None:
    await adb.execute(
        text(
            "INSERT INTO authors (name, name_key, open_library_author_id)"
            " VALUES ('Russ Crandall', 'russ crandall', :id)"
        ),
        {"id": CRANDALL},
    )
    book = await _manual(admin, authors=())
    other = await _manual(admin, title="Another Book Of His", authors=(), isbn=None)
    await _plain_crandall(adb, book, other)
    assert (await _link(admin, book, HERITAGE)).status_code == 200
    # The plain record is still credited on the other book, so it stays.
    assert await adb.scalar(text("SELECT count(*) FROM authors")) == 2


# Refusals


async def test_an_open_library_work_that_is_another_book_here_is_refused(admin, adb) -> None:
    first = await _manual(admin)
    assert (await _link(admin, first, WORK)).status_code == 200
    second = await _manual(admin, title="Heritage Cookbook (copy)", isbn=None)
    preview = (await _preview(admin, second, HERITAGE)).json()
    assert "already another book here" in preview["problem"]
    response = await _link(admin, second, HERITAGE)
    assert response.status_code == 409
    assert (
        await adb.scalar(
            text("SELECT open_library_work_id FROM sources WHERE id = :id"), {"id": second}
        )
        is None
    )


async def test_a_book_linked_to_another_work_is_refused(admin, adb) -> None:
    book = await _manual(admin)
    await adb.execute(text("UPDATE sources SET open_library_work_id = 'OL9W'"))
    response = await _link(admin, book, HERITAGE)
    assert response.status_code == 409
    assert "OL9W" in response.json()["detail"]
    assert await adb.scalar(text("SELECT open_library_edition_id FROM editions")) is None


async def test_an_edition_that_is_in_another_book_is_refused(admin, adb, heritage) -> None:
    await _manual(admin)  # holds ISBN 978-0-578-52428-3
    other = await _manual(admin, title="Something Else", authors=(), isbn=None)
    response = await _link(admin, other, HERITAGE)
    assert response.status_code == 409
    assert "another book here" in response.json()["detail"]


async def test_an_edition_with_no_work_is_refused(admin, heritage) -> None:
    orphan = copy.deepcopy(heritage.records["/books/OL28936410M.json"])
    orphan.pop("works", None)
    orphan["key"] = "/books/OL1M"
    heritage.records["/books/OL1M.json"] = orphan
    book = await _manual(admin)
    response = await _link(admin, book, "OL1M")
    assert response.status_code == 409
    assert "without a work" in response.json()["detail"]


async def test_a_reference_open_library_does_not_have(admin) -> None:
    book = await _manual(admin)
    assert (await _preview(admin, book, "OL1W")).status_code == 404
    assert (await _preview(admin, book, "not a book")).status_code == 422


async def test_only_an_admin_can_link(client, broker, heritage, adb) -> None:
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    book = await _manual(client)
    await adb.execute(text("UPDATE users SET role = 'user'"))
    assert (await _preview(client, book, HERITAGE)).status_code == 403
    assert (await _link(client, book, HERITAGE)).status_code == 403
    assert heritage.requests == []


async def test_another_sites_page_cannot_link(admin) -> None:
    book = await _manual(admin)
    response = await admin.post(
        f"/api/sources/{book}/open-library",
        json={"reference": HERITAGE},
        headers={"Origin": "https://auth.openlarder.com"},
    )
    assert response.status_code == 403
