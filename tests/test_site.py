"""The band above the header (routers/site.py)."""

from fake_broker import _settings


async def test_a_site_that_isnt_production_says_so(client, configure) -> None:
    configure(_settings(environment="development"))
    site = (await client.get("/api/site")).json()
    assert not site["production"]
    assert "development site" in site["notice"]
    configure(_settings(environment="Staging"))
    assert "staging site" in (await client.get("/api/site")).json()["notice"]


async def test_production_shows_nothing_unless_theres_a_notice(client, configure) -> None:
    configure(_settings(environment="production"))
    assert (await client.get("/api/site")).json() == {
        "environment": "production",
        "production": True,
        "notice": None,
        "analytics_host": None,
    }
    configure(_settings(environment="production", notice="  Down for   upkeep at 9pm. "))
    assert (await client.get("/api/site")).json()["notice"] == "Down for upkeep at 9pm."


async def test_the_site_says_where_page_views_are_counted(client, configure) -> None:
    assert (await client.get("/api/site")).json()["analytics_host"] is None
    configure(
        _settings(umami_script_url="https://stats.openlarder.com/script.js", umami_website_id="abc")
    )
    assert (await client.get("/api/site")).json()["analytics_host"] == "stats.openlarder.com"
