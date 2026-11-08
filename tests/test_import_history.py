"""Import history: a run's totals and report lines, recorded as it goes."""

import csv
import io
import uuid

import pytest
from sqlalchemy import text

from fake_broker import _sign_in


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(text("UPDATE users SET is_admin = true"))
    return client


@pytest.fixture
async def book(adb):
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    await adb.execute(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:w, '9780393541113')"), {"w": work}
    )
    return work


def _item(work, row, title, page="1", ingredients=("Flour",)):
    return {
        "row": row,
        "source_id": str(work),
        "isbn13": "9780393541113",
        "title": title,
        "page": page,
        "ingredients": list(ingredients),
    }


async def _start(client, **changes):
    body = {"books_in_list": 2, "recipes_in_file": 4, "untitled_rows": [9], **changes}
    response = await client.post("/api/import/runs", json=body)
    assert response.status_code == 201
    return response.json()["id"]


async def test_a_run_records_totals_and_lines_batch_by_batch(admin, book) -> None:
    run = await _start(admin)
    items = [
        _item(book, 2, "Cake"),
        _item(book, 3, "Bare", ingredients=()),
        _item(uuid.uuid4(), 4, "Lost"),
    ]
    await admin.post("/api/import/recipes", json={"run_id": run, "items": items})
    await admin.post(
        f"/api/import/runs/{run}/lines",
        json={"lines": [{"book": "Other Book", "kind": "book_not_added", "detail": "404"}]},
    )
    await admin.post(
        f"/api/import/runs/{run}/finish",
        json={"books_added": 1, "books_existing": 0, "books_failed": 1},
    )

    (listed,) = (await admin.get("/api/import/runs")).json()
    assert listed["id"] == run
    assert listed["finished_at"] is not None
    assert listed["started_by"] is None  # the fake broker's user has chosen no name
    assert {
        k: listed[k]
        for k in (
            "recipes_created",
            "recipes_skipped",
            "recipes_not_imported",
            "flags_raised",
            "books_added",
            "books_failed",
        )
    } == {
        "recipes_created": 2,
        "recipes_skipped": 0,
        "recipes_not_imported": 2,  # the untitled row and the lost book
        "flags_raised": 1,
        "books_added": 1,
        "books_failed": 1,
    }
    assert listed["lines"] == 4


async def test_a_run_left_open_still_shows_what_it_did(admin, book) -> None:
    run = await _start(admin)
    await admin.post("/api/import/recipes", json={"run_id": run, "items": [_item(book, 2, "Cake")]})
    (listed,) = (await admin.get("/api/import/runs")).json()
    assert listed["finished_at"] is None
    assert listed["recipes_created"] == 1


async def test_the_report_downloads_with_book_names_from_flagged_recipes(admin, book) -> None:
    run = await _start(admin, untitled_rows=[])
    await admin.post(
        "/api/import/recipes",
        json={"run_id": run, "items": [_item(book, 5, "Bare", page=None, ingredients=())]},
    )
    response = await admin.get(f"/api/import/runs/{run}/report.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == ["Row", "Book", "Recipe", "What", "Detail"]
    assert sorted(r[3] for r in rows[1:]) == ["no ingredients", "no page"]
    assert {r[1] for r in rows[1:]} == {"Pink Cake"}


async def test_a_finished_run_takes_no_more(admin, book) -> None:
    run = await _start(admin)
    await admin.post(
        f"/api/import/runs/{run}/finish",
        json={"books_added": 0, "books_existing": 0, "books_failed": 0},
    )
    late = await admin.post(
        "/api/import/recipes", json={"run_id": run, "items": [_item(book, 2, "Cake")]}
    )
    assert late.status_code == 409


async def test_only_admins_see_or_write_history(client, broker) -> None:
    assert (await client.get("/api/import/runs")).status_code == 401
    await _sign_in(client, broker)
    assert (await client.get("/api/import/runs")).status_code == 403
    body = {"books_in_list": 0, "recipes_in_file": 0}
    assert (await client.post("/api/import/runs", json=body)).status_code == 403


async def test_another_sites_page_cannot_start_a_run(admin) -> None:
    response = await admin.post(
        "/api/import/runs",
        json={"books_in_list": 0, "recipes_in_file": 0},
        headers={"Origin": "https://auth.openlarder.com"},
    )
    assert response.status_code == 403


async def test_recipes_the_browser_could_not_place_count_as_not_imported(admin) -> None:
    run = await _start(admin, untitled_rows=[])
    lines = [
        {"row": 7, "book": "Not In List", "recipe": "Stew", "kind": "not_imported", "detail": "x"},
        {"book": "Broken Book", "kind": "book_not_added", "detail": "404"},
    ]
    await admin.post(f"/api/import/runs/{run}/lines", json={"lines": lines})
    (listed,) = (await admin.get("/api/import/runs")).json()
    assert (listed["recipes_not_imported"], listed["lines"]) == (1, 2)
