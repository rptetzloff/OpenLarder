"""Authors' facts from Wikidata (wikidata.py, author_facts.py)."""

import pytest
from sqlalchemy import text

from fake_broker import _sign_in, make_admins
from fake_wikidata import row
from openlarder import wikidata as wikidata_client


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


async def _author(adb, name, *, ol=None, q=None, kind="person"):
    return str(
        await adb.scalar(
            text(
                "INSERT INTO authors (name, name_key, kind, open_library_author_id, wikidata_id)"
                " VALUES (:n, lower(:n), :k, :ol, :q) RETURNING id"
            ),
            {"n": name, "k": kind, "ol": ol, "q": q},
        )
    )


async def _run(admin):
    response = await admin.post("/api/authors/wikidata")
    assert response.status_code == 200, response.text
    return response.json()


async def test_an_author_is_found_by_open_library_id(admin, client, adb, wikidata) -> None:
    julia = await _author(adb, "Julia Child", ol="OL218264A")
    # Claire Ptak's Open Library record has no Wikidata item.
    claire = await _author(adb, "Claire Ptak", ol="OL7106535A")
    # Nothing to find her by: not asked about.
    await _author(adb, "Nana")
    run = await _run(admin)
    assert (run["checked"], run["found"], run["clashes"], run["remaining"]) == (2, 1, [], 0)
    page = (await client.get(f"/api/authors/{julia}")).json()
    assert page["wikidata_url"] == "https://www.wikidata.org/wiki/Q214477"
    assert (page["born_year"], page["died_year"], page["country"]) == (1912, 2004, "United States")
    none = (await client.get(f"/api/authors/{claire}")).json()
    assert (none["wikidata_url"], none["born_year"], none["country"]) == (None, None, None)
    # Both were asked about now, so a second run has nothing to do.
    assert (await _run(admin))["checked"] == 0
    assert wikidata.user_agents == {wikidata_client.USER_AGENT}


async def test_one_asked_long_ago_is_asked_again(admin, adb, wikidata) -> None:
    await _author(adb, "Claire Ptak", ol="OL7106535A")
    await _run(admin)
    await adb.execute(text("UPDATE authors SET wikidata_checked_at = now() - interval '31 days'"))
    assert (await _run(admin))["checked"] == 1


async def test_an_organisation_is_found_by_its_wikidata_id(admin, client, adb, wikidata) -> None:
    atk = await _author(adb, "America's Test Kitchen", q="Q20926529", kind="organisation")
    await _run(admin)
    page = (await client.get(f"/api/authors/{atk}")).json()
    assert page["website"] == "https://www.americastestkitchen.com/"


async def test_founded_died_and_two_countries_are_read(admin, client, adb, wikidata) -> None:
    wikidata.by_q.append(row("Q1", born="1950-06-01T00:00:00Z", countryLabel="Italy"))
    wikidata.by_q.append(row("Q1", born="1950-06-01T00:00:00Z", countryLabel="France"))
    wikidata.by_q.append(row("Q1", website="http://example.com/a/long/page"))
    wikidata.by_q.append(row("Q1", website="https://example.com/"))
    someone = await _author(adb, "Someone", q="Q1")
    await _run(admin)
    page = (await client.get(f"/api/authors/{someone}")).json()
    assert (page["born_year"], page["country"], page["website"]) == (
        1950,
        "France and Italy",
        "https://example.com/",
    )


async def test_an_item_another_author_has_is_reported_not_taken(admin, adb, wikidata) -> None:
    held = await _author(adb, "Julia Child", q="Q214477")
    other = await _author(adb, "Julia McWilliams Child", ol="OL218264A")
    run = await _run(admin)
    assert run["clashes"] == [
        {
            "author": {"id": other, "name": "Julia McWilliams Child", "sources": 0},
            "other": {"id": held, "name": "Julia Child", "sources": 0},
        }
    ]
    assert (
        await adb.scalar(text("SELECT wikidata_id FROM authors WHERE id = :i"), {"i": other})
        is None
    )


async def test_wikidata_down_changes_nothing(admin, adb, wikidata) -> None:
    await _author(adb, "Julia Child", ol="OL218264A")
    wikidata.fail_with = 503
    response = await admin.post("/api/authors/wikidata")
    assert response.status_code == 502
    assert await adb.scalar(text("SELECT wikidata_checked_at FROM authors")) is None


async def test_an_admin_gives_the_item_by_link(admin, client, adb, wikidata) -> None:
    atk = await _author(adb, "America's Test Kitchen", kind="organisation")
    given = await admin.put(
        f"/api/authors/{atk}/wikidata",
        json={"reference": "https://www.wikidata.org/wiki/Q20926529"},
    )
    assert given.status_code == 200, given.text
    assert given.json()["website"] == "https://www.americastestkitchen.com/"
    # One Wikidata doesn't have is refused, and the old one kept.
    missing = await admin.put(f"/api/authors/{atk}/wikidata", json={"reference": "Q999999999"})
    assert missing.status_code == 422
    assert (await client.get(f"/api/authors/{atk}")).json()["wikidata_url"].endswith("Q20926529")
    # Taking it off takes the facts too.
    cleared = await admin.put(f"/api/authors/{atk}/wikidata", json={"reference": None})
    assert (cleared.json()["wikidata_url"], cleared.json()["website"]) == (None, None)


async def test_an_item_another_author_has_is_refused(admin, adb, wikidata) -> None:
    await _author(adb, "Julia Child", q="Q214477")
    other = await _author(adb, "J. Child")
    refused = await admin.put(f"/api/authors/{other}/wikidata", json={"reference": "Q214477"})
    assert refused.status_code == 409
    assert refused.json()["detail"]["author"]["name"] == "Julia Child"


@pytest.mark.parametrize("reference", ["", "not an id", "OL218264A"])
async def test_a_bad_reference_is_refused_or_clears(admin, adb, wikidata, reference) -> None:
    someone = await _author(adb, "Someone")
    response = await admin.put(f"/api/authors/{someone}/wikidata", json={"reference": reference})
    # Empty means take it off; anything else must name an item.
    assert response.status_code == (200 if reference == "" else 422)
    assert wikidata.queries == []


async def test_only_admins_ask_wikidata(admin, adb, wikidata) -> None:
    someone = await _author(adb, "Someone", ol="OL218264A")
    await adb.execute(text("UPDATE users SET role = 'user'"))
    assert (await admin.post("/api/authors/wikidata")).status_code == 403
    assert (
        await admin.put(f"/api/authors/{someone}/wikidata", json={"reference": "Q214477"})
    ).status_code == 403


async def test_ids_that_could_change_the_query_are_left_out(wikidata) -> None:
    import httpx2

    found = await wikidata_client.lookup(
        open_library_ids=['OL1A" } ?x ?y ?z . { "'],
        wikidata_ids=["Q1 } DELETE"],
        transport=httpx2.MockTransport(wikidata.handle),
    )
    assert found == {} and wikidata.queries == []


async def test_merging_keeps_the_facts_with_their_item(admin, client, adb, wikidata) -> None:
    julia = await _author(adb, "Julia Child", ol="OL218264A")
    await _run(admin)
    kept = await _author(adb, "Julia Child (cook)")
    merged = await admin.post(f"/api/authors/{julia}/merge", json={"into": kept})
    assert merged.status_code == 200, merged.text
    page = (await client.get(f"/api/authors/{kept}")).json()
    assert (page["wikidata_url"], page["born_year"]) == (
        "https://www.wikidata.org/wiki/Q214477",
        1912,
    )
