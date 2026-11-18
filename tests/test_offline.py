"""The page shown when there's no connection (web/public/offline.html), the
service worker that keeps it (web/public/sw.js), and how main.py serves
them. *Ray, 2026-11-17: the installable web app.* That the page is shown
when a page can't be fetched is asked of a browser, in the accessibility
check; here, that what the worker keeps is whole and stands alone."""

import re
from pathlib import Path

import pytest

from openlarder.main import FRESH, spa_response
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


def test_the_worker_keeps_that_page_and_nothing_else() -> None:
    [kept] = re.findall(r'const OFFLINE = "(/[^"]+)";', WORKER)
    assert (PUBLIC / kept.lstrip("/")).is_file()
    # One page added to what's kept, and nothing put there as it's fetched.
    assert WORKER.count("cache.add(") == 1
    assert "cache.put(" not in WORKER and "addAll(" not in WORKER
    # Only a page being opened is its business.
    assert 'event.request.mode !== "navigate" || event.request.method !== "GET"' in WORKER


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
