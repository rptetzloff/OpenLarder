"""API keys, and the rate limit on reading /api from outside the site."""

import httpx2
import pytest
from sqlalchemy import text

from fake_broker import _settings, _sign_in
from openlarder import ratelimit
from openlarder.main import app


@pytest.fixture
def small_limits(monkeypatch):
    settings = _settings(
        api_reads_per_minute=3,
        api_searches_per_minute=2,
        api_requests_per_day=8,
        api_key_reads_per_minute=5,
        api_key_searches_per_minute=4,
        api_key_requests_per_day=50,
    )
    monkeypatch.setattr(ratelimit, "get_settings", lambda: settings)


@pytest.fixture
async def outside(configure):
    """A program, not the site's pages: no Sec-Fetch-Site."""
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


async def _key(client, broker, name="Meal planner"):
    await _sign_in(client, broker)
    made = await client.post("/api/account/keys", json={"name": name})
    assert made.status_code == 201, made.text
    return made.json()


# Keys


async def test_a_key_is_shown_once_then_listed_without_it(client, broker, adb) -> None:
    made = await _key(client, broker, "  Meal   planner ")
    assert made["name"] == "Meal planner"
    assert made["key"].startswith("ol_") and made["prefix"] == made["key"][:10]
    listed = (await client.get("/api/account/keys")).json()
    assert [(k["name"], k["prefix"]) for k in listed] == [("Meal planner", made["prefix"])]
    assert "key" not in listed[0]
    # Only its hash is kept.
    stored = await adb.scalar(text("SELECT token_hash FROM api_keys"))
    assert made["key"].encode() not in bytes(stored)


async def test_five_keys_at_most_and_a_name_needed(client, broker) -> None:
    await _key(client, broker, "1")
    for n in range(2, 6):
        assert (await client.post("/api/account/keys", json={"name": str(n)})).status_code == 201
    assert (await client.post("/api/account/keys", json={"name": "6"})).status_code == 409
    assert (await client.post("/api/account/keys", json={"name": " "})).status_code == 422


async def test_only_its_owner_revokes_a_key(client, broker, people) -> None:
    made = await _key(client, broker)
    bo = await people("bo")
    assert (await bo.delete(f"/api/account/keys/{made['id']}")).status_code == 404
    assert (await client.delete(f"/api/account/keys/{made['id']}")).status_code == 204
    assert (await client.get("/api/account/keys")).json() == []


async def test_signed_out_there_are_no_keys(client) -> None:
    assert (await client.get("/api/account/keys")).status_code == 401


# The limit


async def test_without_a_key_the_limit_is_per_address(outside, small_limits) -> None:
    for left in (2, 1, 0):
        ok = await outside.get("/api/tags")
        assert ok.status_code == 200
        assert (ok.headers["ratelimit-limit"], ok.headers["ratelimit-remaining"]) == (
            "3",
            str(left),
        )
        assert ok.headers["ratelimit-policy"] == "3;w=60, 8;w=86400"
    over = await outside.get("/api/tags")
    assert over.status_code == 429
    assert int(over.headers["retry-after"]) >= 1
    assert over.headers["cache-control"] == "no-store"
    assert "API key" in over.json()["detail"]
    # Another address has its own count.
    other = await outside.get("/api/tags", headers={"CF-Connecting-IP": "203.0.113.9"})
    assert other.status_code == 200


async def test_the_sites_own_pages_are_never_limited(client, small_limits) -> None:
    for _ in range(10):
        assert (await client.get("/api/tags")).status_code == 200


async def test_a_key_raises_the_limit(client, broker, outside, small_limits, adb) -> None:
    key = (await _key(client, broker))["key"]
    for n in range(5):
        # Either header.
        headers = {"Authorization": f"Bearer {key}"} if n % 2 else {"X-API-Key": key}
        assert (await outside.get("/api/tags", headers=headers)).status_code == 200
    over = await outside.get("/api/tags", headers={"Authorization": f"Bearer {key}"})
    assert over.status_code == 429
    assert await adb.scalar(text("SELECT last_used_at FROM api_keys")) is not None


async def test_a_wrong_or_revoked_key_is_refused(client, broker, outside, small_limits) -> None:
    made = await _key(client, broker)
    for wrong in ("ol_not-a-real-key", "something-else"):
        refused = await outside.get("/api/tags", headers={"Authorization": f"Bearer {wrong}"})
        assert refused.status_code == 401
    await client.delete(f"/api/account/keys/{made['id']}")
    gone = await outside.get("/api/tags", headers={"X-API-Key": made["key"]})
    assert gone.status_code == 401


async def test_only_api_reads_are_counted(outside, small_limits) -> None:
    for _ in range(6):
        assert (await outside.get("/healthz")).status_code == 200
        assert (await outside.get("/api/auth/me")).status_code == 401


async def test_a_key_reads_what_someone_signed_out_sees(people, outside, adb) -> None:
    """Ann's key doesn't open her private collection."""
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Gran's Box", "acknowledged": True})
    ).json()["id"]
    key = (await ann.post("/api/account/keys", json={"name": "Mine"})).json()["key"]
    assert (await ann.get(f"/api/sources/{box}")).status_code == 200
    with_key = await outside.get(f"/api/sources/{box}", headers={"X-API-Key": key})
    assert with_key.status_code == 404


async def test_searches_have_their_own_smaller_limit(outside, small_limits) -> None:
    for path in ("/api/search?q=cake", "/api/sources?q=cake"):
        assert (await outside.get(path)).status_code == 200
    over = await outside.get("/api/ingredients?q=salt")
    assert over.status_code == 429
    assert "searches a minute" in over.json()["detail"]
    # Plain reads still have their own.
    assert (await outside.get("/api/tags")).status_code == 200


async def test_the_daily_cap_counts_every_request(outside, monkeypatch) -> None:
    roomy = _settings(api_reads_per_minute=100, api_searches_per_minute=100, api_requests_per_day=4)
    monkeypatch.setattr(ratelimit, "get_settings", lambda: roomy)
    for path in ("/api/tags", "/api/search?q=x", "/api/tags", "/api/sources?q=y"):
        assert (await outside.get(path)).status_code == 200
    capped = await outside.get("/api/tags")
    assert capped.status_code == 429
    assert "today" in capped.json()["detail"]
    assert 1 <= int(capped.headers["retry-after"]) <= 86400


async def test_the_limits_as_set_are_published(client, configure) -> None:
    configure(_settings(api_reads_per_minute=7, api_key_requests_per_day=70000))
    shown = (await client.get("/api/account/api-limits")).json()
    assert shown["without_key"]["reads_per_minute"] == 7
    assert shown["with_key"]["requests_per_day"] == 70000
