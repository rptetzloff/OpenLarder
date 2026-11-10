"""Books: ISBNs, the Open Library lookup, adding, and reading back.

Open Library is faked at the HTTP layer from responses saved from the real
API (tests/data/openlibrary, public domain), so the parser is tested
against real shapes. The edge cases are hand-made variants of those.
"""

import copy

import httpx2
import pytest
from sqlalchemy import text

from fake_broker import _sign_in, make_admins
from fake_openlibrary import PINK_CAKE
from openlarder import isbn, openlibrary


@pytest.fixture
async def admin(client, broker, adb, openlib):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


async def _add(client, raw: str) -> httpx2.Response:
    return await client.post("/api/sources", json={"isbn": raw})


# ISBNs


@pytest.mark.parametrize(
    "raw, isbn13",
    [
        ("9780393541113", "9780393541113"),
        ("978-0-393-54111-3", "9780393541113"),
        ("0-306-40615-2", "9780306406157"),  # the standard ISBN-10 worked example
        ("080442957X", "9780804429573"),  # an X check digit
        ("080442957x", "9780804429573"),
    ],
)
def test_isbns_normalise_to_isbn13(raw, isbn13) -> None:
    assert isbn.normalise(raw) == isbn13


@pytest.mark.parametrize(
    "raw", ["", "12345", "9780393541114", "0306406153", "9770393541113", "97803935411130"]
)
def test_bad_isbns_are_refused(raw) -> None:
    with pytest.raises(isbn.InvalidIsbn):
        isbn.normalise(raw)


# The Open Library lookup


async def test_the_lookup_reads_real_open_library_records(openlib) -> None:
    found = await openlibrary.find_by_isbn(PINK_CAKE, httpx2.MockTransport(openlib.handle))
    assert found.title == "Love Is a Pink Cake"
    assert found.subtitle == "Irresistible Bakes and Treats for Morning, Noon, and Night"
    assert (found.open_library_work_id, found.edition_id) == ("OL29227890W", "OL40203348M")
    assert [a.name for a in found.authors] == ["Claire Ptak"]
    assert (found.published_year, found.cover_id) == (2023, 14125211)
    assert found.publisher == "Norton & Company, Incorporated, W. W."


async def test_the_lookup_identifies_openlarder(openlib) -> None:
    await openlibrary.find_by_isbn(PINK_CAKE, httpx2.MockTransport(openlib.handle))
    assert openlib.user_agents == {openlibrary.USER_AGENT}
    assert "privacy@openlarder.com" in openlibrary.USER_AGENT


@pytest.mark.parametrize(
    "publish_date, year",
    [("2023", 2023), ("March 7, 2023", 2023), ("c1998", 1998), ("", None), ("n.d.", None)],
)
def test_publication_years_are_read_from_free_text(publish_date, year) -> None:
    assert openlibrary._year(publish_date) == year


# Adding


async def test_adding_a_book_stores_work_edition_and_author(admin, adb) -> None:
    response = await _add(admin, "978-0-393-54111-3")
    assert response.status_code == 201
    source_id = response.json()["id"]

    book = (await admin.get(f"/api/sources/{source_id}")).json()
    assert book["title"] == "Love Is a Pink Cake"
    assert [c["credited_as"] for c in book["credits"]] == ["Claire Ptak"]
    (edition,) = book["editions"]
    assert edition["isbn13"] == PINK_CAKE
    assert edition["title"] is None  # same as the work's
    assert edition["cover_url"] == "/covers/14125211-M.jpg"
    assert edition["open_library_url"] == "https://openlibrary.org/books/OL40203348M"
    assert book["recipes"] == []


async def test_a_second_isbn_of_the_same_work_joins_it(admin, adb, openlib) -> None:
    openlib.add_edition("9781399611329", title="Love Is a Pink Cake (UK)", publish_date="2023")
    first = (await _add(admin, PINK_CAKE)).json()["id"]
    second = (await _add(admin, "9781399611329")).json()["id"]

    assert first == second
    assert await adb.scalar(text("SELECT count(*) FROM sources")) == 1
    assert await adb.scalar(text("SELECT count(*) FROM authors")) == 1
    titles = {e["title"] for e in (await admin.get(f"/api/sources/{first}")).json()["editions"]}
    assert titles == {None, "Love Is a Pink Cake (UK)"}


async def test_an_author_is_shared_across_books(admin, adb, openlib) -> None:
    other_work = copy.deepcopy(openlib.records["/works/OL29227890W.json"])
    other_work.update({"title": "Another Book", "key": "/works/OL1W"})
    openlib.records["/works/OL1W.json"] = other_work
    openlib.add_edition("9780306406157", works=[{"key": "/works/OL1W"}])
    await _add(admin, PINK_CAKE)
    await _add(admin, "9780306406157")

    assert await adb.scalar(text("SELECT count(*) FROM sources")) == 2
    assert await adb.scalar(text("SELECT count(*) FROM authors")) == 1


async def test_adding_the_same_isbn_twice_points_at_the_book(admin, openlib) -> None:
    first = (await _add(admin, PINK_CAKE)).json()["id"]
    lookups = len(openlib.requests)
    again = await _add(admin, "0393541118")  # the same book's ISBN-10

    assert again.status_code == 409
    assert again.json()["detail"]["source_id"] == first
    assert len(openlib.requests) == lookups  # answered without asking Open Library


async def test_an_isbn_open_library_does_not_know(admin) -> None:
    response = await _add(admin, "9780306406157")
    assert (response.status_code, response.json()["detail"]) == (
        404,
        "Open Library has no book with that ISBN.",
    )


async def test_open_library_down_is_a_502_and_stores_nothing(admin, adb, openlib) -> None:
    openlib.fail_with = 503
    assert (await _add(admin, PINK_CAKE)).status_code == 502
    assert await adb.scalar(text("SELECT count(*) FROM sources")) == 0


async def test_a_bad_isbn_is_refused_before_any_lookup(admin, openlib) -> None:
    response = await _add(admin, "9780393541114")
    assert response.status_code == 422
    assert openlib.requests == []


async def test_only_an_admin_can_add(client, broker, openlib) -> None:
    assert (await _add(client, PINK_CAKE)).status_code == 401
    await _sign_in(client, broker)
    assert (await _add(client, PINK_CAKE)).status_code == 403
    assert openlib.requests == []


async def test_another_sites_page_cannot_add(admin) -> None:
    response = await admin.post(
        "/api/sources", json={"isbn": PINK_CAKE}, headers={"Origin": "https://auth.openlarder.com"}
    )
    assert response.status_code == 403


# Reading


async def test_the_list_is_public_and_alphabetical(admin, client, openlib) -> None:
    other_work = copy.deepcopy(openlib.records["/works/OL29227890W.json"])
    other_work.update({"title": "apple pies", "key": "/works/OL2W"})
    openlib.records["/works/OL2W.json"] = other_work
    openlib.add_edition("9780306406157", works=[{"key": "/works/OL2W"}], covers=[])
    await _add(admin, PINK_CAKE)
    await _add(admin, "9780306406157")
    await admin.post("/api/auth/logout")

    books = (await client.get("/api/sources")).json()["sources"]
    assert [b["title"] for b in books] == ["apple pies", "Love Is a Pink Cake"]
    assert books[0]["cover_url"] == "/covers/14125211-M.jpg"
    assert books[1]["authors"] == ["Claire Ptak"]
    assert books[1]["editions"] == 1


async def test_an_unknown_book_is_a_404(client) -> None:
    response = await client.get("/api/sources/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_the_database_refuses_a_cover_id_that_is_not_positive(db) -> None:
    from sqlalchemy.exc import IntegrityError

    work = db.execute(
        text("INSERT INTO sources (title) VALUES ('Covers') RETURNING id")
    ).scalar_one()
    insert = "INSERT INTO editions (source_id, open_library_cover_id) VALUES (:w, :c)"
    for bad in (0, -1):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(text(insert), {"w": work, "c": bad})
    db.execute(text(insert), {"w": work, "c": 14125211})
