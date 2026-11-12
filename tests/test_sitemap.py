"""The sitemap: every page that's everyone's, in files of at most 50,000,
and nothing that isn't (routers/sitemaps.py). *Ray's spec, 2026-11-11.*"""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest
from sqlalchemy import text

from fake_broker import _settings, _sign_in, make_admins
from openlarder.routers import sitemaps

NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
SITE = "http://testserver"


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


async def _book(admin, title, authors=("Ann Author",)):
    added = await admin.post("/api/sources/manual", json={"title": title, "authors": list(authors)})
    assert added.status_code == 200, added.text
    return added.json()["id"]


async def _recipe(c, source, title, ingredients):
    # A book's recipe says which edition it's in; a family collection has none.
    editions = (await c.get(f"/api/sources/{source}")).json()["editions"]
    body = {"title": title, "ingredients": list(ingredients)}
    if editions:
        body["editions"] = [{"edition_id": editions[0]["id"], "page": "1"}]
    made = await c.post(f"/api/sources/{source}/recipes", json=body)
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def _listed(client, path) -> list[str]:
    """The addresses a sitemap file or the index lists, in its order."""
    response = await client.get(path)
    assert response.status_code == 200, (path, response.text)
    assert response.headers["content-type"].startswith("application/xml")
    assert response.headers["cache-control"] == "public, max-age=3600"
    root = ElementTree.fromstring(response.text)
    return [loc.text for loc in root.findall(".//s:loc", NS)]


async def test_the_sitemap_lists_every_public_page_by_kind(admin, adb, client) -> None:
    book = await _book(admin, "Plenty")
    bread = await _recipe(admin, book, "Bread", ["Egg", "Flour"])
    egg, flour = [
        str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": n}))
        for n in ("Egg", "Flour")
    ]
    ann = str(await adb.scalar(text("SELECT id FROM authors WHERE name = 'Ann Author'")))
    assert await _listed(client, "/sitemap.xml") == [
        f"{SITE}/sitemaps/{kind}-1.xml" for kind in ("recipes", "sources", "ingredients", "authors")
    ]
    assert await _listed(client, "/sitemaps/recipes-1.xml") == [f"{SITE}/recipes/{bread}"]
    assert await _listed(client, "/sitemaps/sources-1.xml") == [f"{SITE}/sources/{book}"]
    assert sorted(await _listed(client, "/sitemaps/ingredients-1.xml")) == sorted(
        [f"{SITE}/ingredients/{egg}", f"{SITE}/ingredients/{flour}"]
    )
    assert await _listed(client, "/sitemaps/authors-1.xml") == [f"{SITE}/authors/{ann}"]


async def test_each_page_says_the_day_it_last_changed(admin, adb, client) -> None:
    book = await _book(admin, "Plenty")
    changed = await adb.scalar(
        text("SELECT to_char(updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') FROM sources")
    )
    root = ElementTree.fromstring((await client.get("/sitemaps/sources-1.xml")).text)
    assert [(u.find("s:loc", NS).text, u.find("s:lastmod", NS).text) for u in root] == [
        (f"{SITE}/sources/{book}", changed)
    ]
    # The day in UTC, wherever the database's clock is set.
    late = datetime(2026, 3, 4, 20, 30, tzinfo=timezone(timedelta(hours=-6)))
    assert sitemaps._day(late) == "2026-03-05"


async def test_an_empty_catalog_has_an_empty_index(client) -> None:
    assert await _listed(client, "/sitemap.xml") == []
    for path in ("/sitemaps/recipes-1.xml", "/sitemaps/recipes-0.xml", "/sitemaps/secrets-1.xml"):
        response = await client.get(path)
        assert response.status_code == 404, path
        # Not kept: the first record may arrive a minute from now.
        assert response.headers["cache-control"] == "no-store"


async def test_a_kind_is_split_into_files_of_the_limit(admin, client, monkeypatch) -> None:
    book = await _book(admin, "Plenty")
    made = sorted([await _recipe(admin, book, f"Recipe {n}", []) for n in range(5)])
    monkeypatch.setattr(sitemaps, "PER_FILE", 2)
    index = await _listed(client, "/sitemap.xml")
    assert [a for a in index if "/recipes-" in a] == [
        f"{SITE}/sitemaps/recipes-{n}.xml" for n in (1, 2, 3)
    ]
    # In a fixed order, each once, across the files.
    files = [await _listed(client, f"/sitemaps/recipes-{n}.xml") for n in (1, 2, 3)]
    assert [len(f) for f in files] == [2, 2, 1]
    assert [a for f in files for a in f] == [f"{SITE}/recipes/{r}" for r in made]
    assert (await client.get("/sitemaps/recipes-4.xml")).status_code == 404


async def test_addresses_are_the_sites_public_ones(admin, client, configure) -> None:
    book = await _book(admin, "Plenty")
    configure(_settings().model_copy(update={"public_url": "https://openlarder.com"}))
    assert "https://openlarder.com/sitemaps/sources-1.xml" in await _listed(client, "/sitemap.xml")
    assert await _listed(client, "/sitemaps/sources-1.xml") == [
        f"https://openlarder.com/sources/{book}"
    ]


@pytest.mark.parametrize("who", ["nobody", "bob", "admin", "ann"])
async def test_nothing_private_or_waiting_is_listed(admin, adb, client, people, who) -> None:
    """Whoever asks, its owner included: the sitemap is the same for all."""
    book = await _book(admin, "Open Book")
    shown = await _recipe(admin, book, "Open Bread", ["Butter"])
    waiting = await _recipe(admin, book, "Waiting Pie", ["Waiting Spice"])
    await adb.execute(
        text("UPDATE recipes SET review = 'pending' WHERE id = :r"), {"r": uuid.UUID(waiting)}
    )
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Secret Box", "acknowledged": True})
    ).json()["id"]
    stew = await _recipe(ann, box, "Secret Stew", ["Zanzibar Moonsalt", "Butter"])
    nana = await adb.scalar(
        text(
            "INSERT INTO authors (name, name_key) VALUES ('Nana Secretta', 'nana secretta')"
            " RETURNING id"
        )
    )
    await adb.execute(
        text(
            "INSERT INTO source_credits (source_id, author_id, position, credited_as)"
            " VALUES (:s, :a, 1, 'Nana Secretta')"
        ),
        {"s": uuid.UUID(box), "a": nana},
    )
    named = {
        n: str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": n}))
        for n in ("Butter", "Zanzibar Moonsalt", "Waiting Spice")
    }
    asking = {"nobody": client, "ann": ann}.get(who) or await people(who, admin=who == "admin")
    everything = [
        address
        for kind in ("recipes", "sources", "ingredients", "authors")
        for address in await _listed(asking, f"/sitemaps/{kind}-1.xml")
    ]
    hidden = (box, stew, waiting, named["Zanzibar Moonsalt"], named["Waiting Spice"], str(nana))
    assert not [h for h in hidden if any(h in address for address in everything)]
    # What they're beside is there: an ingredient a public recipe uses too.
    for path in (f"/recipes/{shown}", f"/sources/{book}", f"/ingredients/{named['Butter']}"):
        assert f"{SITE}{path}" in everything


def test_robots_txt_points_at_the_sitemap() -> None:
    robots = (Path(__file__).parent.parent / "web" / "public" / "robots.txt").read_text()
    assert "Sitemap: https://openlarder.com/sitemap.xml" in robots.splitlines()
