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


def test_an_iphone_is_told_how() -> None:
    """*Ray, 2026-11-18: "first iphone offer".* Safari makes no offer a
    page can take up, so on an iPhone or iPad the footer's button says how
    to install it; that it does is asked of a browser told it's an iPhone,
    in the accessibility check. Here, that the button is the one people
    see elsewhere, and that the browser's own offer can't take its place."""
    install = (WEB / "src" / "install.ts").read_text(encoding="utf-8")
    assert "/iPhone|iPad|iPod/.test(navigator.userAgent)" in install
    # An iPad asking for the desktop site says it's a Mac with a touch screen.
    assert 'navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1' in install
    # Opened from its icon already, nothing is said.
    assert ".standalone === true" in install and "(display-mode: standalone)" in install
    app = (WEB / "src" / "App.vue").read_text(encoding="utf-8")
    first = app.index('v-if="installByHand"')
    assert first < app.index('v-else-if="canInstall"')
    assert app.count("        Install the app\n") == 2
    assert 'aria-controls="install-how"' in app and 'id="install-how"' in app
    assert "{{ INSTALL_STEPS }}" in app
    s = install[install.index("export const INSTALL_STEPS =") :]
    assert '"To install OpenLarder on this iPhone or iPad, tap Share (the square with an " +' in s
    assert '"arrow pointing up), then Add to Home Screen. It then opens from its own " +' in s


def test_the_menu_offers_it_where_the_footer_does() -> None:
    """*Ray, 2026-11-18: "you just have to scroll all the way to the bottom
    to see that note".* The header's Menu has it too, on the same terms,
    and says the same words; that pressing it does what the footer's does
    is asked of a browser, in the accessibility check."""
    header = (WEB / "src" / "components" / "SiteHeader.vue").read_text(encoding="utf-8")
    start = header.index('<HeaderMenu id="phone-menu"')
    menu = header[start : header.index("</HeaderMenu>", start)]
    assert '<ul v-if="installByHand || canInstall" class="install">' in menu
    assert menu.count("Install the app") == 2
    assert 'v-if="installByHand"' in menu and '@click="install"' in menu
    assert 'aria-controls="menu-install-how"' in menu and 'id="menu-install-how"' in menu
    assert "{{ INSTALL_STEPS }}" in menu
