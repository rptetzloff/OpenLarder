"""Copies of web recipes' pages from the Internet Archive."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx2
import pytest
from sqlalchemy import text

from fake_archive import FakeArchive
from fake_broker import _settings, _sign_in
from openlarder import archive
from openlarder.archiving import Archiver, get_archiver

PAGE = "https://smittenkitchen.com/2024/04/rhubarb-cake/"
SNAPSHOT = f"https://web.archive.org/web/20261108153000/{PAGE}"
ADDED = datetime(2026, 11, 8, 15, 29, tzinfo=UTC)


def _done(timestamp="20261108153000"):
    return {"status": "success", "timestamp": timestamp, "original_url": PAGE}


# The client


async def test_a_capture_is_waited_for(ia: FakeArchive) -> None:
    ia.statuses = [{"status": "pending"}, {"status": "pending"}, _done()]
    copy = await archive.copy_of(PAGE, ADDED, None, httpx2.MockTransport(ia.handle))
    assert copy == archive.Snapshot(SNAPSHOT, datetime(2026, 11, 8, 15, 30, tzinfo=UTC))
    polls = [r for r in ia.requests if r.url.path == "/save/status/job-1"]
    assert len(polls) == 3


async def test_keys_are_sent_when_there_are_some(ia: FakeArchive) -> None:
    ia.statuses = [_done()]
    await archive.copy_of(PAGE, ADDED, ("access", "secret"), httpx2.MockTransport(ia.handle))
    assert ia.requests[0].headers["authorization"] == "LOW access:secret"
    ia.requests.clear()
    await archive.copy_of(PAGE, ADDED, None, httpx2.MockTransport(ia.handle))
    assert "authorization" not in ia.requests[0].headers
    assert (
        ia.requests[0].content
        == b"url=https%3A%2F%2Fsmittenkitchen.com%2F2024%2F04%2Frhubarb-cake%2F"
    )


@pytest.mark.parametrize(
    "statuses, code",
    [
        (None, 200),  # Save Page Now refuses
        ([{"status": "error", "message": "blocked"}], 200),
        ([_done()], 429),  # too many requests to that site
        ([{"status": "pending"}], 200),  # never finishes
    ],
)
async def test_without_a_capture_the_nearest_copy_to_when_it_was_added(
    ia: FakeArchive, statuses, code
) -> None:
    ia.statuses, ia.save_code = statuses, code
    ia.closest = {
        "available": True,
        "url": f"http://web.archive.org/web/20250101000000/{PAGE}",
        "timestamp": "20250101000000",
        "status": "200",
    }
    copy = await archive.copy_of(PAGE, ADDED, None, httpx2.MockTransport(ia.handle))
    assert copy == archive.Snapshot(
        f"https://web.archive.org/web/20250101000000/{PAGE}", datetime(2025, 1, 1, tzinfo=UTC)
    )
    asked = next(r for r in ia.requests if r.url.host == "archive.org")
    assert asked.url.params["timestamp"] == "20261108152900"


async def test_no_copy_anywhere_is_none(ia: FakeArchive) -> None:
    assert await archive.copy_of(PAGE, ADDED, None, httpx2.MockTransport(ia.handle)) is None


async def test_an_unreachable_archive_is_none_not_an_error() -> None:
    def down(request):
        raise httpx2.ConnectError("no route")

    assert await archive.copy_of(PAGE, ADDED, None, httpx2.MockTransport(down)) is None


# Web recipes


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET is_admin = true"))
    return client


async def _web_recipe(client, address=PAGE):
    site = await client.post("/api/sources/websites", json={"address": address})
    made = await client.post(
        f"/api/sources/{site.json()['id']}/recipes",
        json={"title": "Rhubarb Cake", "web_address": address, "ingredients": ["Rhubarb"]},
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def test_a_web_recipes_page_is_copied_after_saving(admin, ia, client) -> None:
    ia.statuses = [_done()]
    recipe = await _web_recipe(admin)
    page = (await client.get(f"/api/recipes/{recipe}")).json()["web_page"]
    assert page["url"] == PAGE
    assert page["archive_url"] == SNAPSHOT
    assert page["archived_at"].startswith("2026-11-08T15:30")
    assert page["gone"] is False


async def test_a_failed_copy_is_noted_and_the_recipe_still_saved(admin, ia, client, adb) -> None:
    recipe = await _web_recipe(admin)
    page = (await client.get(f"/api/recipes/{recipe}")).json()["web_page"]
    assert page["archive_url"] is None
    tried = await adb.scalar(text("SELECT archive_tried_at FROM web_pages"))
    assert tried is not None


async def test_editing_asks_again_only_while_theres_no_copy(admin, ia, client) -> None:
    recipe = await _web_recipe(admin)
    edit = {"title": "Rhubarb Cake", "web_address": PAGE, "ingredients": ["Rhubarb", "Egg"]}
    ia.statuses = [_done()]
    await admin.put(f"/api/recipes/{recipe}", json=edit)
    assert (await client.get(f"/api/recipes/{recipe}")).json()["web_page"]["archive_url"]
    ia.requests.clear()
    await admin.put(f"/api/recipes/{recipe}", json=edit)
    assert ia.requests == []


async def test_a_books_recipe_asks_nothing(admin, ia, adb) -> None:
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    edition = await adb.scalar(
        text("INSERT INTO editions (source_id) VALUES (:b) RETURNING id"), {"b": book}
    )
    made = await admin.post(
        f"/api/sources/{book}/recipes",
        json={"title": "Cake", "editions": [{"edition_id": str(edition)}], "ingredients": []},
    )
    assert made.status_code == 201
    assert ia.requests == []


# Admin actions


async def _page_id(client, recipe):
    return (await client.get(f"/api/recipes/{recipe}")).json()["web_page"]["id"]


async def test_an_admin_asks_again(admin, ia, client) -> None:
    recipe = await _web_recipe(admin)
    page = await _page_id(client, recipe)
    ia.statuses = [_done()]
    response = await admin.post(f"/api/web-pages/{page}/archive")
    assert (response.status_code, response.json()) == (202, {"pages": 1})
    assert (await client.get(f"/api/recipes/{recipe}")).json()["web_page"][
        "archive_url"
    ] == SNAPSHOT


async def test_an_admin_asks_for_every_page_without_a_copy(admin, ia, adb) -> None:
    for n in range(3):
        await _web_recipe(admin, f"https://smittenkitchen.com/{n}/")
    await adb.execute(
        text(
            "UPDATE web_pages SET archive_url = 'https://web.archive.org/x', archived_at = now()"
            " WHERE url LIKE '%/0/'"
        )
    )
    ia.statuses = [_done()]
    response = await admin.post("/api/web-pages/archive-missing")
    assert response.json() == {"pages": 2}
    left = await adb.scalar(text("SELECT count(*) FROM web_pages WHERE archive_url IS NULL"))
    assert left == 0


async def test_a_page_is_marked_gone_and_back(admin, client) -> None:
    recipe = await _web_recipe(admin)
    page = await _page_id(client, recipe)
    assert (await admin.put(f"/api/web-pages/{page}/gone", json={"gone": True})).json() == {
        "gone": True
    }
    assert (await client.get(f"/api/recipes/{recipe}")).json()["web_page"]["gone"] is True
    await admin.put(f"/api/web-pages/{page}/gone", json={"gone": False})
    assert (await client.get(f"/api/recipes/{recipe}")).json()["web_page"]["gone"] is False


async def test_page_actions_are_for_admins(admin, client, adb) -> None:
    recipe = await _web_recipe(admin)
    page = await _page_id(client, recipe)
    assert (await admin.post(f"/api/web-pages/{uuid.uuid4()}/archive")).status_code == 404
    await adb.execute(text("UPDATE users SET is_admin = false"))
    assert (await admin.post(f"/api/web-pages/{page}/archive")).status_code == 403
    assert (await admin.post("/api/web-pages/archive-missing")).status_code == 403
    gone = await admin.put(f"/api/web-pages/{page}/gone", json={"gone": True})
    assert gone.status_code == 403


async def test_a_failed_capture_stops_asking(ia: FakeArchive) -> None:
    ia.statuses = [{"status": "error", "message": "blocked"}]
    await archive.copy_of(PAGE, ADDED, None, httpx2.MockTransport(ia.handle))
    polls = [r for r in ia.requests if r.url.path == "/save/status/job-1"]
    assert len(polls) == 1


async def test_a_copy_marked_unavailable_is_no_copy(ia: FakeArchive) -> None:
    ia.closest = {"available": False, "url": SNAPSHOT, "timestamp": "20261108153000"}
    assert await archive.copy_of(PAGE, ADDED, None, httpx2.MockTransport(ia.handle)) is None


async def test_turned_off_it_asks_nothing(adb, ia) -> None:
    """For checks that add web recipes without asking the real Archive."""

    @asynccontextmanager
    async def same_session():
        yield adb

    off = Archiver(same_session, None, httpx2.MockTransport(ia.handle), enabled=False)
    await off.run([uuid.uuid4()])
    assert ia.requests == []


def test_the_setting_reaches_the_archiver() -> None:
    assert get_archiver(_settings(archive_web_pages=False)).enabled is False
    assert get_archiver(_settings()).enabled is True
