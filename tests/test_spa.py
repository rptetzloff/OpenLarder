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
