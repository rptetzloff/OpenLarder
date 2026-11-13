"""Book titles in the wrong capitals, or missing an apostrophe: suggested,
never changed unasked (title_rules.py)."""

import json
import uuid

import pytest
from sqlalchemy import text

from openlarder.title_rules import in_title_case, with_apostrophe

# The rules


@pytest.mark.parametrize(
    "title, cased",
    [
        ("Fiery ferments", "Fiery Ferments"),
        ("The grilling book", "The Grilling Book"),
        ("the joy of cooking", "The Joy of Cooking"),
        ("Mastering the art of French cooking", "Mastering the Art of French Cooking"),
        # Short words are capitalised with the rest, once a longer one asks.
        ("Salt, fat, acid, heat", "Salt, Fat, Acid, Heat"),
        ("Fish pie with Chips", "Fish Pie with Chips"),
        # A small word begins the part after a colon or a dash.
        ("Jerusalem: a cookbook", "Jerusalem: A Cookbook"),
        ("Step-by-step bread - a baker's guide", "Step-by-Step Bread - A Baker's Guide"),
        ("Bake (and eat) more bread", "Bake (and Eat) More Bread"),
        # A word with a capital in it is as its book has it.
        ("BBQ for the iPad generation", "BBQ for the iPad Generation"),
        # Letters after a digit aren't a word; a word after its hyphen is.
        ("The 2nd helping of gluten-free baking", "The 2nd Helping of Gluten-Free Baking"),
        ("30-minute meals", "30-Minute Meals"),
        ("A cook’s tour of France", "A Cook’s Tour of France"),
        ("Crème brûlée and other éclairs", "Crème Brûlée and Other Éclairs"),
    ],
)
def test_a_title_in_sentence_case_is_put_in_title_case(title, cased) -> None:
    assert in_title_case(title) == cased
    # And what's suggested is left alone.
    assert in_title_case(cased) is None


@pytest.mark.parametrize(
    "title",
    [
        "Plenty",
        # One lower-case word, or a lower-case first word and nothing after
        # it to go by: styled that way, as far as these can tell.
        "plenty",
        "bills Pie",
        "Healthy in a Hurry",
        # Printed this way: "with" is small in a title, though four letters.
        "Cooking with Fire",
        "Bread from the Oven, into the Fire",
        # No lower-case word of four letters to say it's sentence case.
        "Fish pie",
        "The big pig",
        "THE BIG BOOK",
        # Nothing these can see.
        "Everydaycook",
        "",
        "1,000 лет",
    ],
)
def test_a_title_that_doesnt_look_like_sentence_case_is_left(title) -> None:
    assert in_title_case(title) is None


@pytest.mark.parametrize(
    "title, authors, fixed",
    [
        (
            "Danielle Walkers Healthy in a Hurry",
            ["Danielle Walker"],
            "Danielle Walker's Healthy in a Hurry",
        ),
        # As a catalogue has the name.
        ("Olivers Twist", ["Oliver, Jamie (Chef)"], "Oliver's Twist"),
        # The title's own apostrophe, where it has one.
        (
            "Mark’s Kitchen and Marks Daily Bread",
            ["Mark Bittman"],
            "Mark’s Kitchen and Mark’s Daily Bread",
        ),
        ("walkers Kitchen", ["Danielle WALKER"], "walker's Kitchen"),
    ],
)
def test_an_authors_name_with_an_s_gets_its_apostrophe(title, authors, fixed) -> None:
    assert with_apostrophe(title, authors) == fixed
    assert with_apostrophe(fixed, authors) is None


@pytest.mark.parametrize(
    "title, authors",
    [
        # The name itself ends in s.
        ("Williams Sonoma Bread", ["Chris Williams"]),
        ("Williams Sonoma Bread", ["William Smith", "Kate Williams"]),
        # Not before a capitalised word.
        ("Marks kitchen", ["Mark Bittman"]),
        ("Baking with the Walkers", ["Danielle Walker"]),
        ("The Walkers, Baking", ["Danielle Walker"]),
        # Not an author of this book.
        ("Olivers Twist", ["Ann Author"]),
        ("Olivers Twist", []),
        # Too short to be a name: "In" isn't "Ins".
        ("Ins Garden", ["In Kim"]),
    ],
)
def test_other_words_ending_in_s_are_left(title, authors) -> None:
    assert with_apostrophe(title, authors) is None


# The queue


@pytest.fixture
async def mo(people):
    return await people("mo", role="moderator")


@pytest.fixture
async def ad(people):
    return await people("ad", admin=True)


async def _book(who, title, authors=("Ann Author",)):
    made = await who.post("/api/sources/manual", json={"title": title, "authors": list(authors)})
    assert made.status_code in (200, 201), made.text
    return made.json()["id"]


async def _queue(who, kind="title_case", **params):
    listed = await who.get("/api/suggestions", params={"kind": kind, **params})
    assert listed.status_code == 200, listed.text
    return listed.json()["suggestions"]


async def _title(client, source):
    return (await client.get(f"/api/sources/{source}")).json()["title"]


async def test_a_book_added_in_sentence_case_is_suggested_and_accepting_changes_it(
    mo, client
) -> None:
    book = await _book(mo, "The grilling book")
    await _book(mo, "Plenty")
    # Nothing is changed by its being noticed.
    assert await _title(client, book) == "The grilling book"
    (found,) = await _queue(mo)
    assert found["title"] == {
        "source_id": book,
        "was": "The grilling book",
        "proposed": "The Grilling Book",
        "exists": True,
        "unchanged": True,
    }
    assert (found["kind"], found["actionable"], found["model"]) == ("title_case", True, "rules")

    accepted = await mo.post(f"/api/suggestions/{found['id']}/accept", json={})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert await _title(client, book) == "The Grilling Book"
    assert await _queue(mo) == []
    # The change is the moderator's, marked with what suggested it.
    changes = (await mo.get(f"/api/sources/{book}/history")).json()
    assert f"suggestion:{found['id']}" in json.dumps(changes)


async def test_a_lost_apostrophe_is_suggested_from_the_books_author(mo, client) -> None:
    book = await _book(mo, "Danielle Walkers Healthy in a Hurry", ["Danielle Walker"])
    await _book(mo, "Olivers Twist")
    (found,) = await _queue(mo, "title_apostrophe")
    assert found["title"]["proposed"] == "Danielle Walker's Healthy in a Hurry"
    assert await _queue(mo) == []
    done = await mo.post(f"/api/suggestions/{found['id']}/accept", json={})
    assert done.status_code == 200, done.text
    assert await _title(client, book) == "Danielle Walker's Healthy in a Hurry"


async def test_a_dismissed_change_isnt_suggested_for_that_book_again(mo, ad, client, adb) -> None:
    book = await _book(mo, "bills basics")
    (found,) = await _queue(mo)
    assert (await mo.post(f"/api/suggestions/{found['id']}/dismiss")).status_code == 200
    assert await _title(client, book) == "bills basics"

    again = await ad.post("/api/suggestions/titles")
    assert (again.status_code, again.json()) == (200, {"suggested": 0})
    assert await _queue(mo) == []
    # Another title, another question.
    await adb.execute(
        text("UPDATE sources SET title = 'bills open kitchen' WHERE id = :s"), {"s": book}
    )
    assert (await ad.post("/api/suggestions/titles")).json() == {"suggested": 1}
    assert [s["title"]["proposed"] for s in await _queue(mo)] == ["Bills Open Kitchen"]
    # Asked twice, suggested once.
    assert (await ad.post("/api/suggestions/titles")).json() == {"suggested": 0}


async def test_only_an_administrator_asks_for_the_whole_catalog(mo, client) -> None:
    assert (await mo.post("/api/suggestions/titles")).status_code == 403
    assert (await client.post("/api/suggestions/titles")).status_code == 401


async def test_a_title_changed_since_can_only_be_dismissed(mo, client, adb) -> None:
    book = await _book(mo, "The homemade pantry")
    (found,) = await _queue(mo)
    await adb.execute(
        text("UPDATE sources SET title = 'The Homemade Larder' WHERE id = :s"), {"s": book}
    )
    (shown,) = await _queue(mo)
    assert (shown["actionable"], shown["title"]["unchanged"]) == (False, False)
    refused = await mo.post(f"/api/suggestions/{found['id']}/accept", json={})
    assert refused.status_code == 409 and "changed" in refused.json()["detail"]
    assert await _title(client, book) == "The Homemade Larder"
    assert (await mo.post(f"/api/suggestions/{found['id']}/dismiss")).status_code == 200


async def test_a_book_that_has_gone_can_only_be_dismissed(mo, adb) -> None:
    book = await _book(mo, "The vanishing book")
    (found,) = await _queue(mo)
    await adb.execute(text("DELETE FROM sources WHERE id = :s"), {"s": book})
    (shown,) = await _queue(mo)
    assert (shown["actionable"], shown["title"]["exists"]) == (False, False)
    refused = await mo.post(f"/api/suggestions/{found['id']}/accept", json={})
    assert refused.status_code == 409 and "gone" in refused.json()["detail"]
    assert (await mo.post(f"/api/suggestions/{found['id']}/dismiss")).status_code == 200


async def test_only_books_anyone_can_see_are_read(mo, ad, people, client, adb) -> None:
    """A private collection's title never reaches the moderators' queue; a
    website's is often lower case on purpose; a book waiting for review is
    read when it's approved."""
    ann = await people("ann")
    box = await ann.post(
        "/api/sources/family", json={"title": "grandma's secret recipes", "acknowledged": True}
    )
    assert box.status_code in (200, 201), box.text
    site = await mo.post(
        "/api/sources/websites",
        json={"title": "smitten kitchen", "address": "https://smitten.example"},
    )
    assert site.status_code in (200, 201), site.text
    cy = await people("cy", role="contributor")
    waiting = await _book(cy, "The waiting book")

    assert (await ad.post("/api/suggestions/titles")).json() == {"suggested": 0}
    assert await _queue(mo) == []
    # Not hidden from the queue: never written.
    assert await adb.scalar(text("SELECT count(*) FROM suggestions")) == 0

    approved = await mo.post(f"/api/review/sources/{waiting}", json={"action": "approve"})
    assert approved.status_code == 200, approved.text
    assert [s["title"]["proposed"] for s in await _queue(mo)] == ["The Waiting Book"]


async def test_approving_a_book_with_all_its_recipes_reads_its_title(mo, people) -> None:
    cy = await people("cy", role="contributor")
    waiting = await _book(cy, "The second waiting book")
    assert await _queue(mo) == []
    done = await mo.post(f"/api/review/sources/{waiting}/approve-all")
    assert done.status_code == 200, done.text
    assert [s["title"]["proposed"] for s in await _queue(mo)] == ["The Second Waiting Book"]


async def test_a_suggestion_about_a_hidden_book_is_hidden(mo, ad, people, adb) -> None:
    """The rules read only public books, but nothing else stops a row
    naming a private one: it isn't shown, to a moderator or an
    administrator, and can't be acted on."""
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Secret Box", "acknowledged": True})
    ).json()["id"]
    planted = await adb.scalar(
        text(
            "INSERT INTO suggestions (kind, target, proposal, model, prompt_version)"
            " VALUES ('title_case', CAST(:t AS jsonb), CAST(:p AS jsonb), 'rules', 'x')"
            " RETURNING id"
        ),
        {
            "t": json.dumps({"source_id": box}),
            "p": json.dumps({"source_id": box, "title_now": "Secret Box", "title": "Secret Box!"}),
        },
    )
    for who in (mo, ad):
        listed = (await who.get("/api/suggestions")).json()
        assert listed["suggestions"] == [] and listed["open_by_kind"] == {}
        for action in ("accept", "dismiss"):
            refused = await who.post(f"/api/suggestions/{planted}/{action}", json={})
            assert refused.status_code == 404, action
    assert (
        await adb.scalar(text("SELECT title FROM sources WHERE id = :s"), {"s": uuid.UUID(box)})
    ) == "Secret Box"


async def test_an_imports_end_reads_the_titles(ad, mo, adb) -> None:
    await adb.execute(text("INSERT INTO sources (title) VALUES ('The imported book')"))
    assert await _queue(mo) == []
    run = (
        await ad.post("/api/import/runs", json={"books_in_list": 1, "recipes_in_file": 0})
    ).json()["id"]
    done = await ad.post(
        f"/api/import/runs/{run}/finish",
        json={"books_added": 1, "books_existing": 0, "books_failed": 0},
    )
    assert done.status_code == 200, done.text
    assert [s["title"]["proposed"] for s in await _queue(mo)] == ["The Imported Book"]


async def test_the_queue_takes_only_the_kinds_it_knows(adb) -> None:
    insert = text(
        "INSERT INTO suggestions (kind, target, proposal, model, prompt_version)"
        " VALUES (:k, '{}', '{}', 'rules', 'x')"
    )
    for kind in ("title_case", "title_apostrophe"):
        async with adb.begin_nested():
            await adb.execute(insert, {"k": kind})
            await adb.execute(text("DELETE FROM suggestions WHERE kind = :k"), {"k": kind})
    with pytest.raises(Exception, match="ck_suggestions_kind_known"):
        async with adb.begin_nested():
            await adb.execute(insert, {"k": "title_other"})
