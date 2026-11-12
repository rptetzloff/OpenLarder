"""How a credit's name is shown: a catalogue's form reads as a book prints
it, and what is stored doesn't change (Ray's cleanup pass, section 6)."""

import pytest
from sqlalchemy import text

from fake_broker import _sign_in, make_admins
from openlarder.author_names import display_name, shown_name


@pytest.mark.parametrize(
    "stored, shown",
    [
        ("Walker, Danielle (Chef)", "Danielle Walker"),
        ("Miller, Simone (Chef)", "Simone Miller"),
        ("Bryant, Rachael (Food blogger)", "Rachael Bryant"),
        ("America's Test Kitchen (Firm)", "America's Test Kitchen"),
        ("Reinhart, Peter.", "Peter Reinhart"),
        ("Crandall, Russ", "Russ Crandall"),
        ("Child, Julia (1912-2004)", "Julia Child"),
        ("Beard, James, 1903-1985", "James Beard"),
        ("Smith, John A.", "John A. Smith"),
        ("King, Martin Luther, Jr.", "Martin Luther King Jr."),
        ("López-Alt, J. Kenji", "J. Kenji López-Alt"),
        ("  Claire   Ptak ", "Claire Ptak"),
        # Already as printed: left alone, comma or not.
        ("Yotam Ottolenghi", "Yotam Ottolenghi"),
        ("Sarah Ballantyne, PhD", "Sarah Ballantyne, PhD"),
        ("Mark Hyman, M.D.", "Mark Hyman, M.D."),
        ("Terry Wahls, MD, PhD", "Terry Wahls, MD, PhD"),
        ("Sammy Davis, Jr.", "Sammy Davis, Jr."),
        ("Sunset Books, Inc.", "Sunset Books, Inc."),
        ("Jamie Oliver (and friends) at home", "Jamie Oliver (and friends) at home"),
        ("(Chef)", "(Chef)"),
    ],
)
def test_a_catalogue_form_reads_as_printed(stored, shown) -> None:
    assert display_name(stored) == shown


@pytest.mark.parametrize(
    "credited_as, author, shown",
    [
        # The usual case: the author was cleaned, the credit wasn't.
        ("Walker, Danielle (Chef)", "Danielle Walker", "Danielle Walker"),
        # An admin's fix to the author is what shows, when it's the same name.
        ("Lopez-Alt, J. Kenji", "J. Kenji López-Alt", "J. Kenji López-Alt"),
        # Not the same name: the credit's own, turned round.
        ("Walker, Danielle (Chef)", "Danielle Walker Smith", "Danielle Walker"),
        # The author's is in the catalogue's form too: turned round, not copied.
        ("Walker, Danielle (Chef)", "Walker, Danielle (Chef)", "Danielle Walker"),
        # As the book prints it: untouched, whatever the author is called.
        ("Sarah Ballantyne, PhD", "Sarah Ballantyne", "Sarah Ballantyne, PhD"),
        ("Ottolenghi", "Yotam Ottolenghi", "Ottolenghi"),
    ],
)
def test_a_credit_shows_the_author_or_its_own_name(credited_as, author, shown) -> None:
    assert shown_name(credited_as, author) == shown


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


async def test_it_is_shown_that_way_everywhere_and_stored_as_it_was(admin, adb, client) -> None:
    added = await admin.post(
        "/api/sources/manual",
        json={"title": "Against All Grain", "authors": ["Walker, Danielle (Chef)"]},
    )
    assert added.status_code == 200, added.text
    book = added.json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    recipe = await admin.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Banana Bread",
            "editions": [{"edition_id": edition, "page": "12"}],
            "ingredients": ["banana"],
        },
    )
    assert recipe.status_code == 201, recipe.text

    # The source's page: the name to show, and what's stored for the edit form.
    credit = (await client.get(f"/api/sources/{book}")).json()["credits"][0]
    assert (credit["name"], credit["credited_as"]) == ("Danielle Walker", "Walker, Danielle (Chef)")
    author = credit["author_id"]
    # The sources list, a recipe's page and the ingredient's.
    listed = (await client.get("/api/sources")).json()["sources"]
    assert [s["authors"] for s in listed] == [["Danielle Walker"]]
    page = (await client.get(f"/api/recipes/{recipe.json()['id']}")).json()
    assert [c["name"] for c in page["source"]["credits"]] == ["Danielle Walker"]
    banana = page["lines"][0]["options"][0]["ingredient"]["id"]
    used = (await client.get(f"/api/ingredients/{banana}")).json()
    assert [r["authors"] for r in used["recipes"]] == [["Danielle Walker"]]

    # The author's own record is as typed until an admin fixes it; then the
    # fix is what every credit of the same name shows.
    fixed = await admin.patch(
        f"/api/authors/{author}", json={"name": "Danielle Wälker", "kind": "person"}
    )
    assert fixed.status_code == 200, fixed.text
    credit = (await client.get(f"/api/sources/{book}")).json()["credits"][0]
    assert (credit["name"], credit["credited_as"]) == ("Danielle Wälker", "Walker, Danielle (Chef)")
    books = (await client.get(f"/api/authors/{author}")).json()["sources"]
    assert [(b["name"], b["credited_as"]) for b in books] == [
        ("Danielle Wälker", "Walker, Danielle (Chef)")
    ]
    assert [s["authors"] for s in (await client.get("/api/sources")).json()["sources"]] == [
        ["Danielle Wälker"]
    ]
