"""Covers: served from the site's own path, only for editions in the catalog."""

import httpx2
import pytest
from sqlalchemy import text

from openlarder.main import app
from openlarder.routers.covers import covers_transport

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


class FakeCovers:
    def __init__(self) -> None:
        self.requests: list[str] = []
        self.status = 200
        self.content_type = "image/jpeg"

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(str(request.url))
        if self.status != 200:
            return httpx2.Response(self.status)
        return httpx2.Response(200, content=JPEG, headers={"content-type": self.content_type})


@pytest.fixture
def covers(configure) -> FakeCovers:
    fake = FakeCovers()
    app.dependency_overrides[covers_transport] = lambda: httpx2.MockTransport(fake.handle)
    return fake


@pytest.fixture
async def catalogued(adb) -> int:
    work = await adb.scalar(text("INSERT INTO works (title) VALUES ('Pink Cake') RETURNING id"))
    await adb.execute(
        text("INSERT INTO editions (work_id, open_library_cover_id) VALUES (:w, 14125211)"),
        {"w": work},
    )
    return 14125211


async def test_a_catalogued_cover_is_served_and_cached_for_good(client, covers, catalogued) -> None:
    response = await client.get(f"/covers/{catalogued}-M.jpg")
    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    # The literal, not the constant: changing the constant must fail this.
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert covers.requests == ["https://covers.openlibrary.org/b/id/14125211-M.jpg?default=false"]


async def test_a_cover_not_in_the_catalog_is_not_relayed(client, covers, catalogued) -> None:
    response = await client.get("/covers/999-M.jpg")
    assert response.status_code == 404
    # Not cached: the book may be added a minute later.
    assert response.headers["cache-control"] == "no-store"
    assert covers.requests == []


async def test_an_unknown_size_is_not_relayed(client, covers, catalogued) -> None:
    assert (await client.get(f"/covers/{catalogued}-XL.jpg")).status_code == 404
    assert covers.requests == []


@pytest.mark.parametrize("upstream, expected", [(404, 404), (503, 502)])
async def test_a_failed_fetch_is_not_cached(client, covers, catalogued, upstream, expected) -> None:
    covers.status = upstream
    response = await client.get(f"/covers/{catalogued}-M.jpg")
    assert response.status_code == expected
    assert response.headers["cache-control"] == "no-store"


async def test_something_that_is_not_an_image_is_refused(client, covers, catalogued) -> None:
    covers.content_type = "text/html"
    assert (await client.get(f"/covers/{catalogued}-M.jpg")).status_code == 502
