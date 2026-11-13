"""Where signing in goes afterwards, and how it's counted (routers/auth.py).

Against the fake broker (fake_broker.py), so Authlib's real checks and the
app's real routes. What these can't show is a browser following the
redirects: that's checked by signing in on a built image.
"""

import httpx2
import pytest

from fake_broker import _failed, _settings
from openlarder import analytics
from openlarder.auth import NEXT_MAX, SESSION_COOKIE, SIGN_IN_COOKIE, safe_next

UMAMI = {"umami_script_url": "https://stats.openlarder.test/script.js", "umami_website_id": "abc"}


async def _through(client, broker, **params) -> httpx2.Response:
    """Sign in from a link with these parameters; the callback's answer."""
    login = await client.get("/api/auth/login", params=params)
    assert login.status_code == 302, login.text
    code, state = broker.approve(login.headers["location"])
    return await client.get("/api/auth/callback", params={"code": code, "state": state})


async def _named(client, broker) -> None:
    """Someone who has signed in before and chosen a name."""
    assert (await _through(client, broker)).headers["location"] == "/welcome"
    saved = await client.put("/api/account/display-name", json={"display_name": "Test Cook"})
    assert saved.status_code == 200, saved.text


def _went(response: httpx2.Response) -> str:
    assert response.status_code == 303, response.text
    return response.headers["location"]


# The page it began on


async def test_signing_in_comes_back_to_the_page_it_began_on(client, broker) -> None:
    await _named(client, broker)
    page = "/recipes/0b0f3f5e-6f0b-4d53-9d0e-1f2a3b4c5d6e?ed=2&x=a%20b"
    assert _went(await _through(client, broker, next=page)) == page
    # And only that once: the next sign-in, from a link that names no page.
    assert _went(await _through(client, broker)) == "/"


REFUSED = [
    # The spec's four.
    "//evil.example",
    "https://evil.example",
    "/\\evil.example",
    "/api/auth/logout",
    # A browser drops a tab or a newline from an address: "//evil.example".
    "/\t/evil.example",
    "/\n/evil.example",
    # Read with their percent-escapes, as the server reads a path.
    "/%2F%2Fevil.example",
    "/%2f/evil.example",
    "/%5Cevil.example",
    "/%09/evil.example",
    "/%61pi/auth/logout",
    "/%67o/bookshop/1",
    "/go/grocer/instacart/1",
    "/api",
    "/API/sources",
    "http:/evil.example",
    "evil.example",
    "javascript:alert(1)",
    "/ok/../\\evil.example",
    "/search?q=//evil.example",
    "/x#//evil.example",
    # The site's links send no "#", and the callback may add its own.
    "/saved#notes",
    "/x\x7f",
    # Sign-in's own pages: "Sign-in didn't work" for someone it worked for.
    "/sign-in-failed",
    "/welcome",
    "/Welcome/",
    "",
    "/" + "x" * NEXT_MAX,
]

KEPT = [
    "/",
    "/sources",
    "/search?q=cake&i=0b0f3f5e-6f0b-4d53-9d0e-1f2a3b4c5d6e",
    # A slash someone searched for, escaped as the site's own links escape it.
    "/search?q=half%2F%2Fhalf",
    "/invite/AbC_dEf-123",
    "/apiary",
    "/gopher",
    "/@evil.example",
    "/" + "x" * (NEXT_MAX - 1),
]


@pytest.mark.parametrize("value", REFUSED)
def test_a_next_that_isnt_a_page_here_is_refused(value) -> None:
    assert safe_next(value) is None


@pytest.mark.parametrize("value", KEPT)
def test_a_page_here_is_kept_as_written(value) -> None:
    assert safe_next(value) == value


@pytest.mark.parametrize("value", [None, 7, ["/sources"], b"/sources"])
def test_a_next_that_isnt_text_is_refused(value) -> None:
    assert safe_next(value) is None


@pytest.mark.parametrize(
    "value", ["//evil.example", "https://evil.example", "/\\evil.example", "/api/auth/logout"]
)
async def test_a_refused_next_ends_at_the_front_page(client, broker, value) -> None:
    await _named(client, broker)
    assert _went(await _through(client, broker, next=value)) == "/"


async def test_no_next_sends_the_browser_to_another_site(client, broker) -> None:
    """Whatever is asked for, the callback's Location is a path here: one
    slash, then not another, and nothing a browser reads as one."""
    await _named(client, broker)
    for value in [*REFUSED, *KEPT]:
        location = _went(await _through(client, broker, next=value))
        assert location.startswith("/") and not location.startswith("//"), value
        assert "\\" not in location and location.isprintable(), value
        assert location == (value if value in KEPT else "/"), value


async def test_next_is_never_read_from_the_callbacks_address(client, broker) -> None:
    await _named(client, broker)
    for began, expected in ((None, "/"), ("/sources", "/sources")):
        login = await client.get("/api/auth/login", params={"next": began} if began else {})
        code, state = broker.approve(login.headers["location"])
        response = await client.get(
            "/api/auth/callback", params={"code": code, "state": state, "next": "/authors"}
        )
        assert _went(response) == expected


async def test_a_page_from_an_abandoned_try_doesnt_outlive_it(client, broker) -> None:
    await _named(client, broker)
    # Began from /sources, never finished; then from a link naming no page.
    await client.get("/api/auth/login", params={"next": "/sources"})
    assert _went(await _through(client, broker)) == "/"
    # Nor when the later link's page is refused.
    await client.get("/api/auth/login", params={"next": "/sources"})
    assert _went(await _through(client, broker, next="//evil.example")) == "/"


# Someone new


async def test_a_new_account_chooses_a_name_then_goes_on(client, broker) -> None:
    assert _went(await _through(client, broker, next="/sources?q=bread")) == "/welcome"
    welcome = await client.get("/welcome")
    assert welcome.status_code == 200
    assert '<meta name="robots" content="noindex" />' in welcome.text

    saved = await client.put("/api/account/display-name", json={"display_name": "New Cook"})
    assert saved.status_code == 200, saved.text
    assert _went(await client.get("/api/auth/continue")) == "/sources?q=bread"
    # Once: asked again, there's nowhere kept.
    assert _went(await client.get("/api/auth/continue")) == "/"
    # Named now, so the welcome page has nothing for them.
    assert _went(await client.get("/welcome")) == "/"


async def test_someone_who_never_chose_a_name_is_asked_again(client, broker) -> None:
    assert _went(await _through(client, broker)) == "/welcome"
    assert _went(await _through(client, broker, next="/sources")) == "/welcome"
    assert _went(await client.get("/api/auth/continue")) == "/sources"


async def test_the_welcome_page_is_only_for_someone_with_no_name(client, broker) -> None:
    assert _went(await client.get("/welcome")) == "/"
    assert _went(await client.get("/api/auth/continue")) == "/"
    await _named(client, broker)
    assert _went(await client.get("/welcome")) == "/"


# A sign-in that didn't work


async def test_trying_again_keeps_the_page_the_failed_try_began_on(client, broker) -> None:
    await _named(client, broker)
    login = await client.get("/api/auth/login", params={"next": "/sources"})
    code, _ = broker.approve(login.headers["location"])
    failed = await client.get("/api/auth/callback", params={"code": code, "state": "forged"})
    assert _failed(failed) and _went(failed) == "/sign-in-failed"

    # "Try again" names no page; a page given with it is ignored.
    assert _went(await _through(client, broker, again="true", next="/authors")) == "/sources"
    # Used: trying again once more has nothing kept.
    assert _went(await _through(client, broker, again="true")) == "/"


async def test_a_sign_in_link_after_a_failure_replaces_the_page(client, broker) -> None:
    await _named(client, broker)
    login = await client.get("/api/auth/login", params={"next": "/sources"})
    code, _ = broker.approve(login.headers["location"])
    assert _failed(await client.get("/api/auth/callback", params={"code": code, "state": "no"}))
    assert _went(await _through(client, broker, next="/authors")) == "/authors"


# Counted


async def test_a_sign_in_is_marked_on_the_address_it_goes_to(client, broker, configure) -> None:
    configure(_settings(**UMAMI))
    # Someone new, on the way to choose a name.
    assert _went(await _through(client, broker, next="/sources")) == "/welcome#signed-in=new"
    saved = await client.put("/api/account/display-name", json={"display_name": "Test Cook"})
    assert saved.status_code == 200, saved.text
    # Going on from the welcome page isn't a sign-in.
    assert _went(await client.get("/api/auth/continue")) == "/sources"

    again = await _through(client, broker, next="/search?q=cake&i=1")
    assert _went(again) == "/search?q=cake&i=1#signed-in=returning"
    assert _went(await _through(client, broker)) == "/#signed-in=returning"


async def test_counting_a_sign_in_keeps_nothing_in_the_browser(client, broker, configure) -> None:
    """A cookie that's for analytics would bring a consent banner
    (SCOPING.md), so the callback sets the two that signing in needs and
    no other."""
    configure(_settings(**UMAMI))
    for _ in range(2):
        response = await _through(client, broker)
        names = sorted(h.split("=", 1)[0] for h in response.headers.get_list("set-cookie"))
        assert names == sorted([SESSION_COOKIE, SIGN_IN_COOKIE]), names


async def test_nothing_is_marked_where_nothing_counts(client, broker) -> None:
    assert _went(await _through(client, broker)) == "/welcome"
    await _named(client, broker)
    assert _went(await _through(client, broker, next="/sources")) == "/sources"


async def test_a_failed_sign_in_isnt_marked(client, broker, configure) -> None:
    configure(_settings(**UMAMI))
    login = await client.get("/api/auth/login")
    code, _ = broker.approve(login.headers["location"])
    failed = await client.get("/api/auth/callback", params={"code": code, "state": "forged"})
    assert _failed(failed) and _went(failed) == "/sign-in-failed"


def test_the_loader_takes_the_mark_off_and_sends_the_event_without_the_page() -> None:
    """Reads the source: that a browser does this, and sends only this, is
    checked by running it against Umami's own tracker."""
    tag = analytics.loader(_settings(**UMAMI))
    assert "location.hash.match(/^#signed-in=(new|returning)$/)" in tag
    # Off the address before the tracker is asked for, tracked or not.
    assert tag.index("history.replaceState") < tag.index("globalPrivacyControl")
    event = tag[tag.index("if (!mark) return;") :]
    assert 'props.name = "sign-in"' in event and "props.data = { account: mark[1] }" in event
    assert 'props.url = "/"' in event and 'props.title = ""' in event
    assert 'props.referrer = ""' in event
    # Never Umami's track("name", data): that adds the page's whole address.
    assert 'track("' not in tag
    assert "@@" not in tag and "cookie" not in tag
