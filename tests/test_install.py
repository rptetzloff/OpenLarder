"""What installing OpenLarder as an app needs of the site (web/public/
site.webmanifest, and how main.py serves it). *Ray, 2026-11-17: the
installable web app, for now.* Chrome said of the manifest as it was,
"start-url-not-valid": it named no page to open, and no browser offered to
install the site. Whether a browser offers to now is asked of the browser,
on the built image; here, that what it reads stays whole."""

import json
import struct
from pathlib import Path

from openlarder.main import spa_response

WEB = Path(__file__).resolve().parents[1] / "web"
PUBLIC = WEB / "public"
MANIFEST = json.loads((PUBLIC / "site.webmanifest").read_text(encoding="utf-8"))


def _size(png: Path) -> tuple[int, int]:
    """A PNG's width and height, from its header."""
    header = png.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n", png.name
    return struct.unpack(">II", header[16:24])


def test_the_manifest_says_what_a_browser_needs_to_offer_it() -> None:
    # A name, a page to open that is inside what the app covers, and to
    # open without the browser's bars.
    assert MANIFEST["name"] == MANIFEST["short_name"] == "OpenLarder"
    assert MANIFEST["start_url"] == "/"
    assert MANIFEST["start_url"].startswith(MANIFEST["scope"])
    assert MANIFEST["display"] == "standalone"
    # Which app it is, whatever page it was installed from: without an id
    # it is its start_url, and changing that would make it another app.
    assert MANIFEST["id"] == "/"
    # Nothing sends anyone to a store's app in its place.
    assert not MANIFEST.get("prefer_related_applications")
    assert not MANIFEST.get("related_applications")


def test_its_icons_are_there_and_the_sizes_it_says() -> None:
    sizes = set()
    for icon in MANIFEST["icons"]:
        file = PUBLIC / icon["src"].lstrip("/")
        assert file.is_file(), icon["src"]
        assert icon["type"] == "image/png"
        width, height = _size(file)
        assert icon["sizes"] == f"{width}x{height}", icon["src"]
        sizes.add((icon["sizes"], icon.get("purpose", "any")))
    # The two a browser asks for to install, and one it may cut to shape.
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= sizes


def test_its_shortcuts_and_the_page_agree_with_the_site() -> None:
    app = (WEB / "src" / "App.vue").read_text(encoding="utf-8")
    header = (WEB / "src" / "components" / "SiteHeader.vue").read_text(encoding="utf-8")
    for shortcut in MANIFEST["shortcuts"]:
        # Each opens a page the site has, inside what the app covers.
        url = shortcut["url"]
        assert url.startswith(MANIFEST["scope"]) and shortcut["name"]
        assert f'"{url}"' in app or f'"{url}"' in header, url
    # The page names the manifest, and its colour is the one the page's
    # own tag gives the browser's bar.
    index = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<link rel="manifest" href="/site.webmanifest" />' in index
    assert f'<meta name="theme-color" content="{MANIFEST["theme_color"]}" />' in index


def test_the_manifest_is_asked_for_afresh(tmp_path) -> None:
    """A browser reads it again to learn what's changed about the app; an
    old copy kept by it, or by Cloudflare, would keep the app as it was."""
    (tmp_path / "index.html").write_text("<html></html>")
    (tmp_path / "site.webmanifest").write_text("{}")
    (tmp_path / "icon-192.png").write_bytes(b"")
    served = spa_response(tmp_path, "site.webmanifest")
    assert served.path == (tmp_path / "site.webmanifest").resolve()
    assert served.headers["cache-control"] == "no-cache"
    assert served.media_type == "application/manifest+json"
    # Only the manifest: an icon is kept as any file is.
    assert "cache-control" not in spa_response(tmp_path, "icon-192.png").headers
