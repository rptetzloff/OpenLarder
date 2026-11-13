"""Checking a book against Open Library and taking what's ticked; cleaning
Open Library's names."""

import copy

import pytest
from sqlalchemy import text

from fake_broker import _sign_in, make_admins
from fake_openlibrary import PINK_CAKE
from openlarder.openlibrary import clean_name

WORK = "/works/OL29227890W.json"
EDITION = "/books/OL40203348M.json"
PTAK = "/authors/OL7106535A.json"


# Names


@pytest.mark.parametrize(
    "raw, name, kind",
    [
        ("Moore, Russell (Chef)", "Russell Moore", "person"),
        ("America's Test Kitchen (Firm)", "America's Test Kitchen", "organisation"),
        ("Crandall, Russ", "Russ Crandall", "person"),
        ("Child, Julia (1912-2004)", "Julia Child", "person"),
        ("King, Martin Luther, Jr.", "Martin Luther King Jr.", "person"),
        ("Sunset Books, Inc.", "Sunset Books, Inc.", "person"),
        ("Yotam Ottolenghi", "Yotam Ottolenghi", "person"),
        ("  Claire   Ptak ", "Claire Ptak", "person"),
        ("(Chef)", "(Chef)", "person"),
    ],
)
def test_open_library_names_are_cleaned(raw, name, kind) -> None:
    assert clean_name(raw) == (name, kind)


# Checking


@pytest.fixture
async def admin(client, broker, adb, openlib):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    # The edition by its own key, as a check asks for it.
    openlib.records[EDITION] = copy.deepcopy(openlib.records[f"/isbn/{PINK_CAKE}.json"])
    return client


async def _pink_cake(client):
    response = await client.post("/api/sources", json={"isbn": PINK_CAKE})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _check(client, book):
    return await client.post(f"/api/sources/{book}/open-library/check")


def _diffs(response):
    """By kind and field: "title", "edition.publisher", "author.name"."""
    out = {}
    for d in response.json()["differences"]:
        parts = d["key"].split(":")
        out[parts[0] if len(parts) == 1 else f"{parts[0]}.{parts[2]}"] = d
    return out


async def test_a_book_just_added_matches(admin, openlib) -> None:
    book = await _pink_cake(admin)
    response = await _check(admin, book)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "open_library_url": "https://openlibrary.org/works/OL29227890W",
        "differences": [],
    }


async def test_a_check_lists_what_changed_there(admin, openlib, adb) -> None:
    book = await _pink_cake(admin)
    openlib.records[WORK]["title"] = "Love Is a Pink Cake!"
    openlib.records[WORK]["subtitle"] = "Irreverent Recipes"
    openlib.records[PTAK]["name"] = "Ptak, Claire Louise (Baker)"
    openlib.records[EDITION]["publishers"] = ["W. W. Norton"]
    openlib.records[EDITION]["publish_date"] = "March 2024"
    openlib.records[EDITION]["covers"] = [999]
    diffs = _diffs(await _check(admin, book))
    # The edition's own title differs from the book's new one now.
    assert set(diffs) == {
        "title",
        "subtitle",
        "author.name",
        "edition.title",
        "edition.publisher",
        "edition.published_year",
        "edition.cover",
    }
    assert (diffs["title"]["ours"], diffs["title"]["theirs"]) == (
        "Love Is a Pink Cake",
        "Love Is a Pink Cake!",
    )
    author = diffs["author.name"]
    assert (author["ours"], author["theirs"]) == ("Claire Ptak", "Claire Louise Ptak")
    assert diffs["edition.publisher"]["label"] == f"Edition {PINK_CAKE}: publisher"
    year = diffs["edition.published_year"]
    assert (year["ours"], year["theirs"]) == ("2023", "2024")
    assert diffs["edition.cover"]["cover"] is True
    assert diffs["edition.cover"]["theirs"].endswith("999-M.jpg")
    # A check changes nothing.
    assert await adb.scalar(text("SELECT title FROM sources")) == "Love Is a Pink Cake"


async def test_only_what_is_ticked_is_taken(admin, openlib, adb) -> None:
    book = await _pink_cake(admin)
    # Fixed here, which Open Library doesn't say.
    await adb.execute(text("UPDATE sources SET title = 'Love Is A Pink Cake'"))
    openlib.records[PTAK]["name"] = "Ptak, Claire Louise"
    openlib.records[EDITION]["publishers"] = ["W. W. Norton"]
    keys = {d["key"] for d in (await _check(admin, book)).json()["differences"]}
    name_key = next(k for k in keys if k.endswith(":name"))
    response = await admin.post(
        f"/api/sources/{book}/open-library/take", json={"keys": [name_key, "not-a-key"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["taken"] == 1
    # What's left is what wasn't ticked.
    assert {d["key"] for d in response.json()["differences"]} == keys - {name_key}
    assert await adb.scalar(text("SELECT name FROM authors")) == "Claire Louise Ptak"
    assert await adb.scalar(text("SELECT title FROM sources")) == "Love Is A Pink Cake"
    publisher = await adb.scalar(text("SELECT publisher FROM editions"))
    assert publisher != "W. W. Norton"


async def test_taking_the_credits_follows_open_library(admin, openlib, adb, client) -> None:
    book = await _pink_cake(admin)
    openlib.records[WORK]["authors"].append({"author": {"key": "/authors/OL1A"}})
    openlib.records["/authors/OL1A.json"] = {"key": "/authors/OL1A", "name": "Norton (Firm)"}
    diffs = _diffs(await _check(admin, book))
    assert (diffs["credits"]["ours"], diffs["credits"]["theirs"]) == (
        "Claire Ptak",
        "Claire Ptak, Norton",
    )
    await admin.post(f"/api/sources/{book}/open-library/take", json={"keys": ["credits"]})
    shown = (await client.get(f"/api/sources/{book}")).json()
    assert [c["credited_as"] for c in shown["credits"]] == ["Claire Ptak", "Norton"]
    kind = await adb.scalar(text("SELECT kind FROM authors WHERE open_library_author_id = 'OL1A'"))
    assert kind == "organisation"


async def test_an_author_dropped_there_goes_when_credits_are_taken(
    admin, openlib, client, adb
) -> None:
    book = await _pink_cake(admin)
    shown = (await client.get(f"/api/sources/{book}")).json()
    credits = [
        {"author_id": shown["credits"][0]["author_id"], "name": "Claire Ptak", "role": "author"}
    ]
    credits.append({"name": "Someone Added Here", "role": "photographer"})
    await admin.put(
        f"/api/sources/{book}", json={"title": shown["title"], "credits": credits, "editions": []}
    )
    diffs = _diffs(await _check(admin, book))
    assert diffs["credits"]["ours"] == "Claire Ptak, Someone Added Here"
    await admin.post(f"/api/sources/{book}/open-library/take", json={"keys": ["credits"]})
    # Credited nowhere now, with no outside record: gone, not just unlisted.
    names = (await adb.scalars(text("SELECT name FROM authors ORDER BY name"))).all()
    assert names == ["Claire Ptak"]


async def test_an_edition_title_like_the_books_is_no_title(admin, openlib) -> None:
    book = await _pink_cake(admin)
    openlib.records[EDITION]["title"] = "LOVE IS A PINK CAKE"
    assert "edition.title" not in _diffs(await _check(admin, book))
    openlib.records[EDITION]["title"] = "Love Is a Pink Cake (UK)"
    title = _diffs(await _check(admin, book))["edition.title"]
    assert (title["ours"], title["theirs"]) == (None, "Love Is a Pink Cake (UK)")


async def test_a_subtitle_only_the_edition_has_is_offered(admin, openlib) -> None:
    book = await _pink_cake(admin)
    openlib.records[EDITION]["subtitle"] = "Bakes for Every Hour"
    subtitle = _diffs(await _check(admin, book))["subtitle"]
    assert subtitle["theirs"] == "Bakes for Every Hour"


async def test_person_or_organisation_is_offered(admin, adb) -> None:
    book = await _pink_cake(admin)
    await adb.execute(text("UPDATE authors SET kind = 'organisation'"))
    kind = _diffs(await _check(admin, book))["author.kind"]
    # Shown in American spelling; what's stored is the word it always was.
    assert (kind["ours"], kind["theirs"]) == ("organization", "person")
    assert kind["label"].endswith(": person or organization")


async def test_what_open_library_lacks_is_not_offered_as_a_blank(admin, openlib, adb) -> None:
    book = await _pink_cake(admin)
    await adb.execute(text("UPDATE editions SET publisher = 'Norton'"))
    del openlib.records[EDITION]["publishers"]
    del openlib.records[EDITION]["subtitle"]
    assert _diffs(await _check(admin, book)) == {}


async def test_a_book_not_from_open_library_cant_be_checked(admin) -> None:
    added = await admin.post("/api/sources/manual", json={"title": "Family Recipes", "authors": []})
    response = await _check(admin, added.json()["id"])
    assert response.status_code == 409


@pytest.mark.parametrize("fail, status", [(503, 502), (None, 404)])
async def test_open_library_failing_changes_nothing(admin, openlib, adb, fail, status) -> None:
    book = await _pink_cake(admin)
    openlib.records[WORK]["title"] = "Changed"
    if fail:
        openlib.fail_with = fail
    else:
        del openlib.records[WORK]
    for path in ("check", "take"):
        response = await admin.post(
            f"/api/sources/{book}/open-library/{path}", json={"keys": ["title"]}
        )
        assert response.status_code == status
    assert await adb.scalar(text("SELECT title FROM sources")) == "Love Is a Pink Cake"


async def test_only_admins_check(admin, adb) -> None:
    book = await _pink_cake(admin)
    await adb.execute(text("UPDATE users SET role = 'user'"))
    assert (await _check(admin, book)).status_code == 403
    take = await admin.post(f"/api/sources/{book}/open-library/take", json={"keys": []})
    assert take.status_code == 403


async def test_a_new_open_library_author_is_cleaned_when_added(admin, openlib, client) -> None:
    openlib.records[PTAK]["name"] = "Ptak, Claire (Baker)"
    book = await _pink_cake(admin)
    shown = (await client.get(f"/api/sources/{book}")).json()
    assert [c["credited_as"] for c in shown["credits"]] == ["Claire Ptak"]
