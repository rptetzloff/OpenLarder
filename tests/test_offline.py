"""The page shown when there's no connection (web/public/offline.html), the
service worker that keeps it (web/public/sw.js), and how main.py serves
them. *Ray, 2026-11-17: the installable web app.* That the page is shown
when a page can't be fetched is asked of a browser, in the accessibility
check; here, that what the worker keeps is whole and stands alone."""

import re
from pathlib import Path

import pytest

from openlarder.auth import SESSION_LIFETIME
from openlarder.main import FRESH, app, spa_response
from test_colour_tokens import _tokens

WEB = Path(__file__).resolve().parents[1] / "web"
PUBLIC = WEB / "public"
PAGE = (PUBLIC / "offline.html").read_text(encoding="utf-8")
WORKER = (PUBLIC / "sw.js").read_text(encoding="utf-8")


def _page_tokens() -> dict[str, dict[str, str]]:
    def parse(block: str) -> dict[str, str]:
        return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))

    light = re.search(r":root\s*\{(.*?)\}", PAGE, re.S)
    dark = re.search(r':root\[data-theme="dark"\]\s*\{(.*?)\}', PAGE, re.S)
    assert light and dark, "offline.html no longer defines both themes"
    return {"light": parse(light.group(1)), "dark": parse(dark.group(1))}


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_its_colours_are_the_sites(theme) -> None:
    """It can't draw on App.vue, which won't arrive: it has a copy of the
    tokens it uses, and the copy is kept true here."""
    site, page = _tokens()[theme], _page_tokens()[theme]
    assert set(page) == {"bg", "fg", "muted", "link", "focus"}
    for name, colour in page.items():
        assert colour.lower() == site[name].lower(), name
    # And nothing in it is coloured but through them.
    styles = re.sub(
        r":root[^{]*\{.*?\}", "", PAGE.split("<style>")[1].split("</style>")[0], flags=re.S
    )
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(", styles)


def test_it_stands_alone() -> None:
    """Nothing but this page is kept on the device, so whatever it asked
    for wouldn't come."""
    assert not re.search(r"<link\b|<img\b|<iframe\b|\bsrc=|url\(|@import|@font-face", PAGE)
    # It asks for the page that was wanted again, not for one of its own.
    assert '<a href="">Try again</a>' in PAGE
    assert 'window.addEventListener("online"' in PAGE and "location.reload()" in PAGE


def test_it_is_a_page_of_the_sites_and_not_one_to_find() -> None:
    assert '<html lang="en">' in PAGE
    assert "<title>No connection · OpenLarder</title>" in PAGE
    assert '<meta name="robots" content="noindex" />' in PAGE
    assert '<meta name="viewport" content="width=device-width, initial-scale=1.0" />' in PAGE
    # The theme chosen on the site holds here, read as index.html reads it.
    index = (WEB / "index.html").read_text(encoding="utf-8")
    chosen = 'localStorage.getItem("openlarder_theme")'
    assert chosen in PAGE and chosen in index


def _answers(method: str) -> set[str]:
    """Every address the server answers that way. Not the API's own
    description of itself, which leaves out what it doesn't publish
    (the shops' links)."""

    def walk(routes):
        for route in routes:
            if method in (getattr(route, "methods", None) or ()):
                yield route.path
            inner = getattr(getattr(route, "original_router", None), "routes", None)
            if inner:
                yield from walk(inner)

    return set(walk(app.routes))


def _list(name: str) -> list[str]:
    """One of the worker's lists of addresses, as it's written there."""
    [body] = re.findall(rf"const {name} = \[(.*?)\];", WORKER, re.S)
    return re.findall(r'"(/[^"]*)"', body)


def test_the_worker_keeps_one_page_for_everyone() -> None:
    [kept] = re.findall(r'const OFFLINE = "(/[^"]+)";', WORKER)
    assert (PUBLIC / kept.lstrip("/")).is_file()
    # That page is all that is kept where nobody has asked for more: one
    # thing is added to that cache, and nothing is put there as it's fetched.
    assert WORKER.count("cache.add(") == 1 and "addAll(" not in WORKER
    # A device whose switch is off: only a page being opened passes through.
    assert "  if (!on) return;\n" in WORKER


def test_what_it_keeps_for_someone_is_what_the_four_pages_need() -> None:
    """The copy kept where someone has switched it on (*Ray, 2026-11-17:
    "only where switched on"*): the pages are the site's, what they ask
    for is the server's to give, and the page for no connection leads to
    exactly those pages."""
    pages, data = _list("PAGES"), _list("DATA")
    assert pages == ["/larder", "/shelf", "/equipment/mine", "/saved"]
    header = (WEB / "src" / "components" / "SiteHeader.vue").read_text(encoding="utf-8")
    for page in pages:
        assert f'"{page}"' in header, page
    assert re.findall(r'<li><a href="(/[^"]+)">', PAGE) == pages
    # What is kept of someone's is this and no more: who they are, what
    # the site says of itself, and what each of the four pages asks for.
    # Adding to it is adding to what stays on a device, and to the Privacy
    # page.
    assert data == [
        "/api/auth/me",
        "/api/site",
        "/api/larder",
        "/api/shelf",
        "/api/equipment-lists",
        "/api/saved",
        "/api/notes",
        "/api/allergens",
        "/api/diets",
        "/api/grocers",
        "/api/kitchen-shops",
    ]
    # Each is a GET the server answers, for someone signed in.
    gets = _answers("GET")
    for address in data:
        assert address in gets, address
    # And each is asked for by the site: who is signed in, and each page's own.
    sources = "".join(f.read_text(encoding="utf-8") for f in (WEB / "src").rglob("*.*"))
    for address in data:
        assert f'"{address}"' in sources or f"`{address}`" in sources, address


def test_it_keeps_each_saved_recipe_and_no_other() -> None:
    """*Ray, 2026-11-17: "yes, as the next PR".* A saved recipe and its
    owner's notes on it are kept, so its page can be read; which recipes
    is what the saved list says, and the site says when that changes."""
    [pattern] = re.findall(r"const RECIPE = /(.*)/;", WORKER)
    kept = re.compile(pattern.replace(r"\/", "/"))
    one = "0a1b2c3d-0000-4000-8000-123456789abc"
    assert kept.match(f"/api/recipes/{one}") and kept.match(f"/api/recipes/{one}/notes")
    # Nothing else of a recipe's, and nothing that isn't one recipe.
    for other in ("/flags", "/rating", "/history", "/notes/x"):
        assert not kept.match(f"/api/recipes/{one}{other}"), other
    for other in ("/api/recipes", "/api/recipes/", "/api/recipes/check", f"/api/saved/{one}"):
        assert not kept.match(other), other
    # Both are GETs the server answers.
    assert {"/api/recipes/{recipe_id}", "/api/recipes/{recipe_id}/notes"} <= _answers("GET")
    # One only looked at isn't kept: a recipe's answer is taken into the
    # copy only where the copy has that recipe already.
    assert "  if (RECIPE.test(path) && !(await cache.match(path))) return;\n" in WORKER
    # Their own list, and so many of it.
    assert "?.recipes;" in WORKER and ".shared" not in WORKER
    assert re.findall(r"const MOST = (\d+);", WORKER) == ["200"]
    assert ".slice(0, MOST);" in WORKER
    # The page of one that is kept is opened from the copy; any other
    # recipe's is the page for no connection.
    assert "(recipe && (await copy(`/api/recipes/${recipe[1]}`)))" in WORKER
    # Saving and taking off the list both tell the worker.
    saved = (WEB / "src" / "saved.ts").read_text(encoding="utf-8")
    assert saved.count(".then(told);") == 2 and "savedChanged();" in saved
    asked = (WEB / "src" / "offline.ts").read_text(encoding="utf-8")
    assert 'postMessage({ type: "saved" })' in asked
    assert 'if (event.data?.type === "saved") event.waitUntil(resaved());' in WORKER
    # A recipe's page is the recipe, with or without its flags, which the
    # copy doesn't hold.
    page = (WEB / "src" / "pages" / "RecipePage.vue").read_text(encoding="utf-8")
    assert "flags.value = await recipeFlags(props.id).catch(() => []);" in page
    privacy = " ".join(
        (WEB / "src" / "pages" / "PrivacyPage.vue").read_text(encoding="utf-8").split()
    )
    assert "each recipe you have saved with your notes on it" in privacy


def test_the_copy_goes_when_its_owner_does() -> None:
    """What ends a session by the site's own forms is what the worker
    takes the copy off for, before the request leaves; and a copy is good
    for as long as a session is, and no longer."""
    posts = _answers("POST")
    leaving = _list("LEAVING")
    assert leaving == ["/api/auth/logout", "/api/account/delete"]
    for address in leaving:
        assert address in posts, address
    header = (WEB / "src" / "components" / "SiteHeader.vue").read_text(encoding="utf-8")
    assert '<form method="post" action="/api/auth/logout">' in header
    [oldest] = re.findall(r"const OLDEST = ([\d *]+);", WORKER)
    milliseconds = 1
    for factor in oldest.split("*"):
        milliseconds *= int(factor)
    assert milliseconds == SESSION_LIFETIME.total_seconds() * 1000
    # The Privacy page says the same number of days, and that it's off
    # unless switched on.
    privacy = (WEB / "src" / "pages" / "PrivacyPage.vue").read_text(encoding="utf-8")
    said = " ".join(privacy.split())
    assert f"signed in for {SESSION_LIFETIME.days} days" in said
    assert "It is off unless you switch it on, on each device." in said
    # Let go, it stays gone: the copy is opened as the worker starts and
    # when it's switched on, and never by asking whether it's there, which
    # made an empty one after its owner had signed out.
    assert WORKER.count("caches.open(YOURS)") == 2
    assert WORKER.count("caches.has(YOURS)") == 1
    # A new worker is no reason to lose it.
    assert "if (name !== KEPT && name !== YOURS) await caches.delete(name);" in WORKER


def test_the_copy_has_one_name_everywhere() -> None:
    [name] = re.findall(r'const YOURS = "([^"]+)";', WORKER)
    asked = (WEB / "src" / "offline.ts").read_text(encoding="utf-8")
    assert f'const YOURS = "{name}";' in asked
    assert f'caches.has("{name}")' in PAGE
    check = (WEB / "a11y" / "check.mjs").read_text(encoding="utf-8")
    assert f'caches.has("{name}")' in check


def test_the_site_asks_for_the_worker_it_has() -> None:
    asked = (WEB / "src" / "offline.ts").read_text(encoding="utf-8")
    [worker] = re.findall(r'serviceWorker\.register\("(/[^"]+)"\)', asked)
    assert (PUBLIC / worker.lstrip("/")).is_file()
    # From the top of the site, which is what lets it answer for every page.
    assert worker.count("/") == 1
    # Not under the dev server, where there's no build to be offline from.
    assert "import.meta.env.PROD" in asked
    app = (WEB / "src" / "App.vue").read_text(encoding="utf-8")
    assert "\nkeepAnOfflinePage();\n" in app


def test_the_worker_and_its_page_are_asked_for_afresh(tmp_path) -> None:
    """A browser fetches the worker again to learn there's a new one, and
    Cloudflare keeps a .js file by its name: an old copy there would leave
    every browser with the worker it had."""
    (tmp_path / "index.html").write_text("<html></html>")
    for name in (*FRESH, "favicon.svg", "robots.txt"):
        (tmp_path / name).write_text("x")
    for name in ("sw.js", "offline.html", "site.webmanifest"):
        served = spa_response(tmp_path, name)
        assert served.path == (tmp_path / name).resolve(), name
        assert served.headers["cache-control"] == "no-cache", name
    for name in ("favicon.svg", "robots.txt"):
        assert "cache-control" not in spa_response(tmp_path, name).headers, name
    # Every one of them is a file the site has.
    for name in FRESH:
        assert (PUBLIC / name).is_file(), name
