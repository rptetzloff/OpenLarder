"""The built SPA: index.html and a missing file are never reused from a cache;
other files are."""

import httpx2
from fastapi import FastAPI

from openlarder.main import Assets, spa_response


def _web(tmp_path):
    (tmp_path / "index.html").write_text("<script src=/assets/index-abc.js></script>")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    return tmp_path


def test_any_page_gets_index_html_that_browsers_must_recheck(tmp_path) -> None:
    web = _web(tmp_path)
    for path in ("", "books", "books/123", "index.html"):
        response = spa_response(web, path)
        assert response.path == web / "index.html", path
        assert response.headers["cache-control"] == "no-cache", path


def test_other_files_are_served_without_that(tmp_path) -> None:
    response = spa_response(_web(tmp_path), "favicon.svg")
    assert response.path == (tmp_path / "favicon.svg").resolve()
    assert "cache-control" not in response.headers


def test_paths_outside_the_build_get_index_html(tmp_path) -> None:
    (tmp_path / "web").mkdir()
    web = _web(tmp_path / "web")
    (tmp_path / "secret.txt").write_text("no")
    response = spa_response(web, "../secret.txt")
    assert response.path == web / "index.html"


async def test_a_missing_asset_is_a_404_nobody_keeps(tmp_path) -> None:
    """A deploy's old server can be asked for the new build's files."""
    (tmp_path / "index-abc.css").write_text("body{}")
    app = FastAPI()
    app.mount("/assets", Assets(directory=tmp_path), name="assets")
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/assets/index-new.css")
        present = await client.get("/assets/index-abc.css")
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-store"
    assert present.status_code == 200
    assert "cache-control" not in present.headers


def test_fonts_go_out_as_fonts() -> None:
    import mimetypes

    import openlarder.main  # noqa: F401  (registers the types)

    assert mimetypes.guess_type("outfit-400.woff2")[0] == "font/woff2"


def test_configured_meta_tags_go_in_every_pages_head(tmp_path) -> None:
    """Site verification (Impact, for Barnes & Noble's affiliate programme)."""
    (tmp_path / "index.html").write_text("<html><head><title>x</title></head><body></body></html>")
    tags = {"impact-site-verification": "56d1-abc", "google-site-verification": 'a"b'}
    for path in ("", "sources/123"):
        response = spa_response(tmp_path, path, tags)
        page = response.body.decode()
        assert (
            '<meta name="impact-site-verification" value="56d1-abc" content="56d1-abc" />'
            '<meta name="google-site-verification" value="a&quot;b" content="a&quot;b" />'
            "</head>"
        ) in page
        assert response.headers["cache-control"] == "no-cache"


def test_a_bad_tag_name_is_refused() -> None:
    import pytest
    from pydantic import ValidationError

    from openlarder.config import Settings

    with pytest.raises(ValidationError):
        Settings(meta_tags={'x" onload="alert(1)': "v"})
    assert Settings(meta_tags={"impact-site-verification": "56d1"}).meta_tags
