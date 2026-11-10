"""Search engines' crawlers aren't rate limited, once verified (crawlers.py)."""

import socket

import httpx2
import pytest

from fake_broker import _settings
from openlarder import crawlers, ratelimit, usage
from openlarder.main import app

GOOGLE = "66.249.79.12"
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


@pytest.fixture
async def outside(configure):
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


@pytest.fixture
def dns(monkeypatch):
    """Google's address reverses to its crawler's name, and back."""
    names = {GOOGLE: "crawl-66-249-79-12.googlebot.com"}
    lookups = []

    def reverse(address):
        lookups.append(address)
        if address not in names:
            raise socket.herror("unknown")
        return names[address], [], [address]

    def forward(host):
        return host, [], [a for a, n in names.items() if n == host]

    monkeypatch.setattr(socket, "gethostbyaddr", reverse)
    monkeypatch.setattr(socket, "gethostbyname_ex", forward)
    monkeypatch.setattr(ratelimit, "get_settings", lambda: _settings(api_reads_per_minute=2))
    return lookups


async def test_a_verified_crawler_isnt_limited_and_is_named(outside, people, dns) -> None:
    for _ in range(5):
        r = await outside.get(
            "/api/tags", headers={"User-Agent": GOOGLEBOT, "CF-Connecting-IP": GOOGLE}
        )
        assert r.status_code == 200
    assert dns == [GOOGLE]  # checked once, then kept
    admin = await people("ada", admin=True)
    [caller] = (await admin.get("/api/admin/api-usage")).json()["callers"]
    assert caller["caller"] == "bot:googlebot" and caller["requests"] == 5


async def test_one_only_claiming_to_be_a_crawler_is_limited(outside, dns) -> None:
    codes = [
        (
            await outside.get(
                "/api/tags", headers={"User-Agent": GOOGLEBOT, "CF-Connecting-IP": "203.0.113.9"}
            )
        ).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]


async def test_a_name_that_doesnt_point_back_isnt_believed(monkeypatch) -> None:
    monkeypatch.setattr(
        socket, "gethostbyaddr", lambda a: ("evil.googlebot.com.example.net", [], [a])
    )
    assert await crawlers.verified(GOOGLEBOT, "198.51.100.1") is None
    monkeypatch.setattr(socket, "gethostbyaddr", lambda a: ("fake.googlebot.com", [], [a]))
    monkeypatch.setattr(socket, "gethostbyname_ex", lambda h: (h, [], ["192.0.2.1"]))
    assert await crawlers.verified(GOOGLEBOT, "198.51.100.2") is None
    assert crawlers.claimed("Mozilla/5.0 Firefox/140.0") is None


async def test_the_daily_cap_survives_a_restart(outside, adb, monkeypatch) -> None:
    monkeypatch.setattr(ratelimit, "get_settings", lambda: _settings(api_requests_per_day=3))
    headers = {"CF-Connecting-IP": "203.0.113.50"}
    for _ in range(2):
        assert (await outside.get("/api/tags", headers=headers)).status_code == 200
    await usage.flush(adb)
    ratelimit.reset()  # as a deploy does
    await ratelimit.resume(adb)
    assert (await outside.get("/api/tags", headers=headers)).status_code == 200
    assert (await outside.get("/api/tags", headers=headers)).status_code == 429


async def test_the_published_ranges_are_believed_without_dns(outside, monkeypatch) -> None:
    def no_reverse(address):
        raise socket.herror("Docker answers no reverse lookups")

    monkeypatch.setattr(socket, "gethostbyaddr", no_reverse)
    crawlers.set_ranges({"googlebot": ["66.249.64.0/19", "2001:4860:4801::/48"]})
    assert await crawlers.verified(GOOGLEBOT, GOOGLE) == "googlebot"
    assert await crawlers.verified(GOOGLEBOT, "2001:4860:4801:10::5") == "googlebot"
    assert await crawlers.verified(GOOGLEBOT, "203.0.113.9") is None


async def test_the_ranges_are_read_from_the_engines_lists() -> None:
    lists = {
        "/static/crawling/ipranges/common-crawlers.json": {
            "prefixes": [{"ipv4Prefix": "66.249.64.0/27"}, {"ipv6Prefix": "2001:4860:4801:10::/64"}]
        },
        "/toolbox/bingbot.json": {"prefixes": [{"ipv4Prefix": "157.55.39.0/24"}]},
    }

    def handle(request):
        found = lists.get(request.url.path)
        return httpx2.Response(200, json=found) if found else httpx2.Response(503)

    await crawlers.refresh(httpx2.MockTransport(handle))
    assert await crawlers.verified(GOOGLEBOT, "66.249.64.3") == "googlebot"
    assert (
        await crawlers.verified("Mozilla/5.0 (compatible; bingbot/2.0)", "157.55.39.1") == "bingbot"
    )
    # Apple's list failed: none, so its claim falls back to DNS.
    assert crawlers._in_ranges("applebot", "17.0.0.1") is None


async def test_api_answers_say_not_to_index_them(client) -> None:
    for path in ("/api/tags", "/api/sources/00000000-0000-0000-0000-000000000000"):
        assert (await client.get(path)).headers["x-robots-tag"] == "noindex", path
