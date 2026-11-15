"""An ad's click id, from the address to a cookie to one row for a new
account (adclicks.py), and what the export's role may do with that row.

Against the fake broker and the real database. What these can't show:
Cloudflare adding the country, a browser carrying the cookie to Authgear
and back, n8n's workflow, and whether Google takes a row. Those are
checked on the site with one real click (README.md).
"""

import hashlib
import re
import time
import uuid
from pathlib import Path

import pytest
from itsdangerous import Signer, TimestampSigner
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fake_broker import _settings
from openlarder import adclicks, dumps, reset
from openlarder.auth import SESSION_COOKIE
from openlarder.config import Settings
from openlarder.main import app

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SECRET = "test-session-secret"
# Mixed case, with both marks a click id may have: it's kept as it came.
GCLID = "TeSt_abc-123456"
US = {"CF-IPCountry": "US"}
DAY = 86400


@pytest.fixture
def on(configure, client):
    """The feature switched on, and a visitor Cloudflare places in the US."""
    configure(_settings(ad_clicks=True))
    client.headers.update(US)
    return client


def _kept(response) -> str | None:
    """The ad cookie's own Set-Cookie header, lowercased, if there is one."""
    found = [
        h for h in response.headers.get_list("set-cookie") if h.startswith(f"{adclicks.COOKIE}=")
    ]
    assert len(found) <= 1, found
    return found[0].lower() if found else None


async def _sign_up(client, broker, **headers):
    """Sign in through the broker; the callback's answer."""
    login = await client.get("/api/auth/login")
    assert login.status_code == 302, login.text
    code, state = broker.approve(login.headers["location"])
    done = await client.get(
        "/api/auth/callback", params={"code": code, "state": state}, headers=headers
    )
    assert done.status_code == 303 and "sign-in-failed" not in done.headers["location"], done.text
    return done


async def _rows(adb) -> list:
    found = await adb.execute(
        text(
            "SELECT kind, click_id, click_id_type, clicked_at, converted_at, exported_at"
            " FROM ad_conversions ORDER BY click_id"
        )
    )
    return found.all()


# The address


@pytest.mark.parametrize(
    "query, found",
    [
        ({"gclid": GCLID}, ("gclid", GCLID)),
        ({"gbraid": "0AAAAAo4mICH_abcdef"}, ("gbraid", "0AAAAAo4mICH_abcdef")),
        ({"wbraid": "0AAAAAo4mICH-abcdef"}, ("wbraid", "0AAAAAo4mICH-abcdef")),
        # The first of the three that's there, in that order.
        ({"wbraid": "w" * 12, "gbraid": "b" * 12, "gclid": "g" * 12}, ("gclid", "g" * 12)),
        ({"wbraid": "w" * 12, "gbraid": "b" * 12}, ("gbraid", "b" * 12)),
        ({"q": "cake"}, None),
        ({}, None),
    ],
)
def test_the_first_click_id_in_the_address_is_the_one(query, found) -> None:
    assert adclicks.click_in(query) == found


@pytest.mark.parametrize(
    "value",
    [
        "",
        "short",
        "a" * 9,
        "a" * 513,
        "has space in it",
        "semi;colon;here",
        "dot.dot.dot.dot",
        "é" * 12,
    ],
)
def test_what_doesnt_look_like_a_click_id_is_ignored(value) -> None:
    assert adclicks.click_in({"gclid": value}) is None
    # And isn't passed over for the next one.
    assert adclicks.click_in({"gclid": value, "gbraid": "b" * 12}) is None


def test_the_longest_and_shortest_are_taken() -> None:
    assert adclicks.click_in({"gclid": "a" * 10}) == ("gclid", "a" * 10)
    assert adclicks.click_in({"gclid": "a" * 512}) == ("gclid", "a" * 512)


# Who may be kept


@pytest.mark.parametrize(
    "headers, may",
    [
        ({"cf-ipcountry": "US"}, True),
        ({"cf-ipcountry": "ca"}, True),
        ({"cf-ipcountry": "US", "sec-gpc": "1"}, False),
        ({"cf-ipcountry": "US", "dnt": "1"}, False),
        # Only "1" asks: DNT's "0" is consent to tracking, said out loud.
        ({"cf-ipcountry": "US", "dnt": "0", "sec-gpc": "0"}, True),
        ({"cf-ipcountry": "DE"}, False),
        ({"cf-ipcountry": "de"}, False),
        ({"cf-ipcountry": "GB"}, False),
        ({"cf-ipcountry": "CH"}, False),
        ({"cf-ipcountry": "NO"}, False),
        ({"cf-ipcountry": "RE"}, False),
        # Nobody can say where these are, so nothing is kept.
        ({}, False),
        ({"cf-ipcountry": ""}, False),
        ({"cf-ipcountry": "XX"}, False),
        ({"cf-ipcountry": "T1"}, False),
    ],
)
def test_who_may_be_kept(headers, may) -> None:
    assert adclicks.may_keep(headers) is may


def test_the_countries_are_the_eea_the_uk_and_switzerland() -> None:
    assert len(adclicks.EU) == 27
    assert adclicks.EEA_UK_CH - adclicks.EU == {"IS", "LI", "NO", "GB", "CH"}
    assert adclicks.EEA_UK_CH <= adclicks.COUNTRIES
    assert not {"US", "CA", "AU", "NZ", "MX"} & adclicks.COUNTRIES


# The cookie's value


def test_a_cookie_opens_to_the_click_it_was_made_from() -> None:
    now = time.time()
    value = adclicks.sealed(SECRET, "gclid", GCLID, now)
    assert value.startswith(f"gclid.{int(now)}.{GCLID}.")
    assert adclicks.opened(SECRET, value, now + 5) == adclicks.Click("gclid", int(now), GCLID)


def test_a_cookie_nobody_here_signed_opens_to_nothing() -> None:
    now = time.time()
    value = adclicks.sealed(SECRET, "gclid", GCLID, now)
    plain = f"gclid.{int(now)}.{GCLID}"
    for forged in (
        value.replace(GCLID, "Another_click-0001"),
        value.replace("gclid.", "gbraid.", 1),
        value[:-2],
        plain,
        "",
        "nonsense",
        adclicks.sealed("another-secret", "gclid", GCLID, now),
        # Signed with the right key for something else: the sign-in cookie's
        # signer, and this one's own with no salt.
        TimestampSigner(SECRET).sign(plain).decode(),
        Signer(SECRET).sign(plain).decode(),
        Signer(SECRET, digest_method=hashlib.sha256).sign(plain).decode(),
    ):
        assert adclicks.opened(SECRET, forged, now) is None, forged


def test_a_cookie_older_than_ninety_days_opens_to_nothing() -> None:
    now = time.time()
    value = adclicks.sealed(SECRET, "gclid", GCLID, now)
    assert adclicks.opened(SECRET, value, now + 90 * DAY - 5) is not None
    assert adclicks.opened(SECRET, value, now + 90 * DAY + 5) is None
    # Nor one from later than now, past what two clocks may differ by.
    assert adclicks.opened(SECRET, value, now - 60) is not None
    assert adclicks.opened(SECRET, value, now - 600) is None


def test_a_signed_value_that_isnt_a_click_opens_to_nothing() -> None:
    signer = Signer(SECRET, salt=adclicks.SALT, digest_method=hashlib.sha256)
    now = int(time.time())
    for plain in (
        f"msclkid.{now}.{GCLID}",
        f"gclid.soon.{GCLID}",
        f"gclid.{now}.short",
        f"gclid.{now}",
        "gclid",
    ):
        assert adclicks.opened(SECRET, signer.sign(plain).decode(), now) is None, plain


def test_it_cant_be_switched_on_without_the_key_that_signs_it() -> None:
    with pytest.raises(ValidationError, match="OPENLARDER_SESSION_SECRET"):
        Settings(ad_clicks=True, session_secret=None)
    assert Settings(ad_clicks=True, session_secret="x").ad_clicks
    assert not Settings(session_secret=None).ad_clicks


# Landing on a page


async def test_landing_from_an_ad_keeps_the_click_in_a_cookie(on) -> None:
    before = time.time()
    landed = await on.get("/", params={"gclid": GCLID})
    assert landed.status_code == 200 and landed.headers["content-type"].startswith("text/html")

    cookie = _kept(landed)
    assert cookie is not None
    for attribute in ("max-age=7776000", "path=/", "httponly", "samesite=lax"):
        assert attribute in cookie.split("; "), cookie
    # http here, so not marked for https only.
    assert "secure" not in cookie.split("; ")
    # Nobody's cache keeps a page with one visitor's cookie on it.
    assert landed.headers["cache-control"] == "no-store"
    assert (await on.get("/", params={"q": "cake"})).headers["cache-control"] == "no-cache"
    click = adclicks.opened(SECRET, on.cookies[adclicks.COOKIE], time.time())
    assert click is not None and (click.type, click.id) == ("gclid", GCLID)
    assert int(before) <= click.at <= time.time()


async def test_on_https_the_cookie_is_for_https_only(on, configure) -> None:
    configure(_settings(ad_clicks=True, public_url="https://openlarder.test"))
    cookie = _kept(await on.get("/sources", params={"wbraid": "0AAAAAo4mICH-abcdef"}))
    assert cookie is not None and "secure" in cookie.split("; ")


async def test_a_newer_click_replaces_an_older_one(on) -> None:
    await on.get("/", params={"gclid": GCLID})
    await on.get("/sources", params={"gbraid": "0AAAAAo4mICH_abcdef"})
    click = adclicks.opened(SECRET, on.cookies[adclicks.COOKIE], time.time())
    assert click is not None and (click.type, click.id) == ("gbraid", "0AAAAAo4mICH_abcdef")
    assert len([c for c in on.cookies.jar if c.name == adclicks.COOKIE]) == 1


async def test_nothing_is_kept_unless_its_switched_on(client) -> None:
    landed = await client.get("/", params={"gclid": GCLID}, headers=US)
    assert landed.status_code == 200 and _kept(landed) is None


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({"Sec-GPC": "1"}, id="global-privacy-control"),
        pytest.param({"DNT": "1"}, id="do-not-track"),
        pytest.param({"CF-IPCountry": "DE"}, id="germany"),
        pytest.param({"CF-IPCountry": "GB"}, id="uk"),
        pytest.param({"CF-IPCountry": "CH"}, id="switzerland"),
        pytest.param({"CF-IPCountry": "XX"}, id="unknown"),
    ],
)
async def test_nothing_is_kept_for_someone_who_mustnt_be(on, headers) -> None:
    landed = await on.get("/", params={"gclid": GCLID}, headers=headers)
    assert landed.status_code == 200 and _kept(landed) is None
    assert adclicks.COOKIE not in on.cookies


async def test_nothing_is_kept_where_cloudflare_names_no_country(on) -> None:
    del on.headers["CF-IPCountry"]
    assert _kept(await on.get("/", params={"gclid": GCLID})) is None


async def test_nothing_is_kept_for_a_click_id_that_isnt_one(on) -> None:
    assert _kept(await on.get("/", params={"gclid": "not one"})) is None
    assert _kept(await on.get("/", params={"q": "gclid=" + GCLID})) is None


async def test_nothing_is_kept_for_someone_signed_in(on, people) -> None:
    ann = await people("ann")
    landed = await ann.get("/", params={"gclid": GCLID}, headers=US)
    assert landed.status_code == 200 and _kept(landed) is None


@pytest.mark.parametrize(
    "path, status, kind",
    [
        # Under /api and not a page, though it's HTML.
        ("/api/docs", 200, "text/html"),
        ("/api/site", 200, "application/json"),
        # Not HTML, so not a page.
        ("/healthz", 200, "application/json"),
        ("/sitemap.xml", 200, "application/xml"),
        # A page there isn't.
        (f"/recipes/{uuid.uuid4()}", 404, "text/html"),
    ],
)
async def test_only_a_page_keeps_it(on, path, status, kind) -> None:
    answer = await on.get(path, params={"gclid": GCLID})
    assert answer.status_code == status, answer.text
    assert answer.headers["content-type"].startswith(kind)
    assert _kept(answer) is None


async def test_only_a_get_keeps_it(on) -> None:
    """Asked of the middleware itself: no page here answers anything but a
    GET, so through the app a HEAD keeps nothing whatever this says."""

    def asked(method: str) -> str | None:
        scope = {
            "type": "http",
            "app": app,
            "method": method,
            "scheme": "http",
            "path": "/",
            "query_string": f"gclid={GCLID}".encode(),
            "headers": [(b"cf-ipcountry", b"US")],
        }
        return adclicks.Middleware(app)._to_keep(scope)

    assert asked("GET").startswith(f"{adclicks.COOKIE}=gclid.")
    for method in ("HEAD", "POST", "PUT", "DELETE"):
        assert asked(method) is None, method


# Signing up


async def test_a_new_account_after_an_ad_click_is_one_row(on, broker, adb) -> None:
    await on.get("/", params={"gclid": GCLID})
    clicked = adclicks.opened(SECRET, on.cookies[adclicks.COOKIE], time.time())
    done = await _sign_up(on, broker)

    (row,) = await _rows(adb)
    assert (row.kind, row.click_id, row.click_id_type) == ("sign_up", GCLID, "gclid")
    assert int(row.clicked_at.timestamp()) == clicked.at
    assert row.exported_at is None
    # The cookie has done its work.
    gone = _kept(done)
    assert gone is not None and "max-age=0" in gone.split("; ")
    assert adclicks.COOKIE not in on.cookies


async def test_the_row_says_nothing_of_whose_account_it_was(on, broker, adb) -> None:
    await on.get("/", params={"gclid": GCLID})
    await _sign_up(on, broker)

    columns = await adb.scalars(
        text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'ad_conversions'"
        )
    )
    assert set(columns) == {
        "id",
        "kind",
        "click_id",
        "click_id_type",
        "clicked_at",
        "converted_at",
        "exported_at",
    }
    # Nor by its time: the account's created_at is the transaction's now()
    # to the microsecond, and the row's is the next whole minute.
    user = (await adb.execute(text("SELECT id, created_at FROM users"))).one()
    row = (
        await adb.execute(
            text(
                "SELECT id, converted_at,"
                " converted_at = date_trunc('minute', converted_at) AS whole,"
                " converted_at > now() AS after,"
                " converted_at <= now() + interval '1 minute' AS soon,"
                " converted_at > clicked_at AS later FROM ad_conversions"
            )
        )
    ).one()
    assert row.whole and row.after and row.soon and row.later
    assert row.converted_at != user.created_at and row.id != user.id
    # And it's no edit: the history has nothing of it.
    assert not await adb.scalar(
        text("SELECT count(*) FROM revisions WHERE table_name = 'ad_conversions'")
    )


async def test_a_returning_account_adds_no_row(on, broker, adb) -> None:
    await _sign_up(on, broker)
    on.cookies.clear()
    await on.get("/", params={"gclid": GCLID})
    assert adclicks.COOKIE in on.cookies

    done = await _sign_up(on, broker)
    assert await _rows(adb) == []
    # Cleared all the same: they have an account now.
    assert "max-age=0" in _kept(done).split("; ")


async def test_a_sign_up_with_no_ad_click_adds_no_row(on, broker, adb) -> None:
    done = await _sign_up(on, broker)
    assert await _rows(adb) == []
    assert _kept(done) is None


async def test_one_click_is_one_sign_up(on, broker, adb) -> None:
    await on.get("/", params={"gclid": GCLID})
    await _sign_up(on, broker)
    # Somebody else's new account, from the same click.
    on.cookies.clear()
    broker.subject = "subject-2"
    await on.get("/", params={"gclid": GCLID})
    await _sign_up(on, broker)

    assert await adb.scalar(text("SELECT count(*) FROM users")) == 2
    assert [r.click_id for r in await _rows(adb)] == [GCLID]


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({"Sec-GPC": "1"}, id="global-privacy-control"),
        pytest.param({"DNT": "1"}, id="do-not-track"),
        pytest.param({"CF-IPCountry": "FR"}, id="france"),
    ],
)
async def test_whats_asked_at_the_click_is_asked_again_at_sign_up(on, broker, adb, headers) -> None:
    await on.get("/", params={"gclid": GCLID})
    done = await _sign_up(on, broker, **headers)
    assert await _rows(adb) == []
    assert "max-age=0" in _kept(done).split("; ")


async def test_switched_off_since_the_click_adds_no_row(on, broker, adb, configure) -> None:
    await on.get("/", params={"gclid": GCLID})
    configure(_settings())
    done = await _sign_up(on, broker)
    assert await _rows(adb) == []
    assert "max-age=0" in _kept(done).split("; ")


async def test_a_cookie_somebody_wrote_adds_no_row(on, broker, adb) -> None:
    on.cookies.set(adclicks.COOKIE, f"gclid.{int(time.time())}.{GCLID}.bm90LWEtc2lnbmF0dXJl")
    await _sign_up(on, broker)
    assert await _rows(adb) == []


async def test_a_failed_sign_in_keeps_the_cookie(on, broker, adb) -> None:
    await on.get("/", params={"gclid": GCLID})
    login = await on.get("/api/auth/login")
    code, _ = broker.approve(login.headers["location"])
    failed = await on.get("/api/auth/callback", params={"code": code, "state": "forged"})
    assert failed.headers["location"] == "/sign-in-failed" and _kept(failed) is None
    assert adclicks.COOKIE in on.cookies and SESSION_COOKIE not in on.cookies


# Kept ninety days, and out of everything else


async def _row(adb, click_id: str, ago: str = "0 days", kind: str = "gclid") -> uuid.UUID:
    return await adb.scalar(
        text(
            "INSERT INTO ad_conversions (kind, click_id, click_id_type, clicked_at, converted_at)"
            " VALUES ('sign_up', :c, :k, now() - CAST(:ago AS interval) - interval '1 hour',"
            " now() - CAST(:ago AS interval)) RETURNING id"
        ),
        {"c": click_id, "k": kind, "ago": ago},
    )


async def test_a_row_goes_ninety_days_after_its_sign_up(adb) -> None:
    await _row(adb, "old-click-0001", "91 days")
    await _row(adb, "newer-click-0002", "89 days")
    assert await adclicks.prune(adb) == 1
    assert [r.click_id for r in await _rows(adb)] == ["newer-click-0002"]
    assert await adclicks.prune(adb) == 0


@pytest.mark.parametrize(
    "columns, values",
    [
        pytest.param(
            "kind, click_id, click_id_type", "'buy_click', 'a-click-id-01', 'gclid'", id="kind"
        ),
        pytest.param(
            "kind, click_id, click_id_type", "'sign_up', 'a-click-id-01', 'msclkid'", id="type"
        ),
        pytest.param("kind, click_id_type", "'sign_up', 'gclid'", id="no-click-id"),
    ],
)
async def test_the_database_refuses_a_row_that_isnt_one(adb, columns, values) -> None:
    with pytest.raises(DBAPIError):
        async with adb.begin_nested():
            await adb.execute(
                text(f"INSERT INTO ad_conversions ({columns}, clicked_at) VALUES ({values}, now())")
            )


async def test_the_data_dump_has_none_of_it(adb) -> None:
    await _row(adb, "dumped-click-0001")
    rows = await dumps.read(adb)
    assert "ad_conversions" not in rows
    assert "dumped-click-0001" not in repr(rows)


async def test_a_catalog_reset_keeps_them_and_everything_doesnt(adb) -> None:
    await _row(adb, "kept-click-0001")
    await reset.reset(adb)
    assert len(await _rows(adb)) == 1
    await reset.reset(adb, everything=True)
    assert await _rows(adb) == []


# The export's role, made by the script itself, running the export's own
# statements.


def _statements() -> dict[str, str]:
    """scripts/ads_export.sql's statements by name, with $1 as :id."""
    parts = re.split(
        r"^-- name: (\w+)$", (SCRIPTS / "ads_export.sql").read_text("utf-8"), flags=re.M
    )
    found = {}
    for name, body in zip(parts[1::2], parts[2::2], strict=True):
        found[name] = re.sub(r"--[^\n]*", "", body).strip().rstrip(";").replace("$1", ":id")
    return found


@pytest.fixture
async def exporter(adb):
    """The script's role under a throwaway name, and a way to act as it."""
    role = f"ads_test_{uuid.uuid4().hex[:8]}"
    database = await adb.scalar(text("SELECT current_database()"))
    script = (
        (SCRIPTS / "ads_role.sql")
        .read_text(encoding="utf-8")
        .replace(':"role"', f'"{role}"')
        .replace(':"DBNAME"', f'"{database}"')
        .replace(":'password'", "'not-a-real-password'")
    )
    script = re.sub(r"--[^\n]*", "", script)
    for statement in filter(str.strip, script.split(";")):
        await adb.execute(text(statement))

    async def as_role(sql, **params):
        # The role goes with the test's rollback, so nothing is dropped after.
        await adb.execute(text(f'SET ROLE "{role}"'))
        try:
            async with adb.begin_nested():
                return await adb.execute(text(sql), params)
        finally:
            await adb.execute(text("RESET ROLE"))

    return as_role


async def test_the_export_reads_whats_new_as_the_sheets_columns(exporter, adb) -> None:
    first = await _row(adb, GCLID, "2 hours")
    second = await _row(adb, "0AAAAAo4mICH_abcdef", "1 hour", "gbraid")
    third = await _row(adb, "0AAAAAo4mICH-abcdef", "0 hours", "wbraid")
    sql = _statements()

    found = await exporter(sql["pending"])
    assert list(found.keys()) == [
        "gclid",
        "gbraid",
        "wbraid",
        "conversion_name",
        "conversion_time",
        "order_id",
    ]
    rows = found.all()
    # Oldest first, one click id column filled in each.
    assert [(r.gclid, r.gbraid, r.wbraid) for r in rows] == [
        (GCLID, "", ""),
        ("", "0AAAAAo4mICH_abcdef", ""),
        ("", "", "0AAAAAo4mICH-abcdef"),
    ]
    assert [r.order_id for r in rows] == [first, second, third]
    assert {r.conversion_name for r in rows} == {"OpenLarder sign-up"}
    for r in rows:
        assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\+00:00", r.conversion_time), r
    said = await adb.scalar(
        text(
            "SELECT to_char(converted_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"
            " FROM ad_conversions WHERE id = :id"
        ),
        {"id": first},
    )
    assert rows[0].conversion_time == said + "+00:00"

    # Marked, a row isn't read again; marking it twice changes nothing.
    assert (await exporter(sql["exported"], id=str(first))).rowcount == 1
    assert (await exporter(sql["exported"], id=str(first))).rowcount == 0
    assert [r.order_id for r in await exporter(sql["pending"])] == [second, third]


async def test_the_exports_role_can_do_nothing_else(exporter, adb) -> None:
    row = await _row(adb, GCLID)
    for sql in (
        "DELETE FROM ad_conversions",
        "INSERT INTO ad_conversions (kind, click_id, click_id_type, clicked_at)"
        " VALUES ('sign_up', 'made-up-click-01', 'gclid', now())",
        "UPDATE ad_conversions SET click_id = 'another-click-01'",
        "UPDATE ad_conversions SET converted_at = now()",
        "TRUNCATE ad_conversions",
        "SELECT 1 FROM users",
        "SELECT 1 FROM user_sessions",
        "SELECT 1 FROM sources",
        "SELECT 1 FROM purchase_clicks",
        "SELECT 1 FROM shops",
        "SELECT 1 FROM revisions",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            await exporter(sql)
    assert await adb.scalar(
        text("SELECT click_id FROM ad_conversions WHERE id = :i"), {"i": row}
    ) == (GCLID)


# The privacy page is told


async def test_the_site_says_whether_ad_clicks_are_kept(client, configure) -> None:
    assert (await client.get("/api/site")).json()["ad_clicks"] is False
    configure(_settings(ad_clicks=True))
    assert (await client.get("/api/site")).json()["ad_clicks"] is True
