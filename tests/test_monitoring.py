"""Admin monitoring: the API's outside callers, and buy-link clicks."""

import httpx2
import pytest
from sqlalchemy import text

from fake_broker import _settings
from openlarder import ratelimit, usage
from openlarder.main import app

IP = "203.0.113.77"


@pytest.fixture
async def outside(configure):
    """A program, not the site's pages."""
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


@pytest.fixture
def tight(monkeypatch):
    settings = _settings(api_reads_per_minute=3, api_searches_per_minute=1)
    monkeypatch.setattr(ratelimit, "get_settings", lambda: settings)


async def test_an_addresss_use_is_kept_under_a_pseudonym(outside, people, adb, tight) -> None:
    for path in ("/api/tags", "/api/tags", "/api/search?q=cake", "/api/search?q=pie"):
        await outside.get(path, headers={"CF-Connecting-IP": IP})
    admin = await people("ada", admin=True)
    page = (await admin.get("/api/admin/api-usage")).json()
    [caller] = page["callers"]
    assert caller["caller"] == f"ip:{usage.pseudonym(IP)}"
    assert caller["network"] == "203.0.113.0/24"
    # Two reads and a search answered; the second search refused.
    assert (caller["requests"], caller["searches"], caller["refused"]) == (3, 1, 1)
    assert caller["today"] == 3 and caller["key_name"] is None
    # The address itself is kept nowhere.
    stored = await adb.scalar(
        text("SELECT string_agg(caller || coalesce(network, ''), ' ') FROM api_usage")
    )
    assert IP not in stored


async def test_a_keys_use_shows_its_name_and_owner_and_can_be_revoked(outside, people, adb) -> None:
    ann = await people("ann")
    key = (await ann.post("/api/account/keys", json={"name": "Meal planner"})).json()
    for _ in range(2):
        await outside.get("/api/tags", headers={"X-API-Key": key["key"]})
    admin = await people("ada", admin=True)
    [caller] = (await admin.get("/api/admin/api-usage")).json()["callers"]
    assert (caller["key_name"], caller["owner"], caller["requests"]) == ("Meal planner", "ann", 2)
    assert (await admin.delete(f"/api/admin/keys/{key['id']}")).status_code == 204
    assert (await outside.get("/api/tags", headers={"X-API-Key": key["key"]})).status_code == 401
    [after] = (await admin.get("/api/admin/api-usage")).json()["callers"]
    assert (after["key_name"], after["requests"]) == ("A revoked key", 2)


async def test_only_admins_see_monitoring(people) -> None:
    bo = await people("bo")
    for path in ("/api/admin/api-usage", "/api/admin/clicks"):
        assert (await bo.get(path)).status_code == 403


def test_a_pseudonym_is_stable_and_needs_the_secret(monkeypatch) -> None:
    assert usage.pseudonym(IP) == usage.pseudonym(IP) != usage.pseudonym("203.0.113.78")
    first = usage.pseudonym(IP)
    from openlarder import usage as module

    monkeypatch.setattr(module, "get_settings", lambda: _settings(session_secret="another"))
    assert usage.pseudonym(IP) != first
    assert usage.network("2001:db8:1:2::5") == "2001:db8:1::/48"
    assert usage.network("not an address") is None


async def test_old_usage_is_dropped(adb) -> None:
    await adb.execute(
        text(
            "INSERT INTO api_usage (day, caller, requests, last_at) VALUES"
            " (current_date - 31, 'ip:old', 5, now()), (current_date - 2, 'ip:new', 5, now())"
        )
    )
    await usage.prune(adb)
    assert list(await adb.scalars(text("SELECT caller FROM api_usage"))) == ["ip:new"]


async def test_clicks_by_shop_book_page_and_day(people, adb) -> None:
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    edition = await adb.scalar(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:w, '9780393541113') RETURNING id"),
        {"w": work},
    )
    await adb.execute(
        text(
            "INSERT INTO purchase_clicks (edition_id, retailer, page, clicked_at) VALUES"
            " (:e, 'bookshop', '/sources/x', now()), (:e, 'bookshop', '/recipes/y', now()),"
            " (:e, 'amazon', '/recipes/y', now() - interval '10 days'),"
            " (:e, 'amazon', '/recipes/y', now() - interval '40 days')"
        ),
        {"e": edition},
    )
    admin = await people("ada", admin=True)
    page = (await admin.get("/api/admin/clicks")).json()
    assert page["clicks"] == 3
    assert [(s["label"], s["clicks"], s["last_7_days"]) for s in page["shops"]] == [
        ("Bookshop.org", 2, 2),
        ("Amazon", 1, 0),
    ]
    assert [(b["title"], b["clicks"]) for b in page["books"]] == [("Pink Cake", 3)]
    assert page["pages"][0] == {"page": "/recipes/y", "clicks": 2}
    assert sum(d["clicks"] for d in page["by_day"]) == 3
