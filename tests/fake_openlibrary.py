"""A fake Open Library, serving responses saved from the real API.

The saved responses (tests/data/openlibrary) are public domain, like all of
Open Library's catalog. Tests add or change records to make edge cases.
"""

import copy
import json
from pathlib import Path

import httpx2

DATA = Path(__file__).parent / "data" / "openlibrary"
PINK_CAKE = "9780393541113"


def _real(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


class FakeOpenLibrary:
    """Serves saved responses by path; tests add or change records."""

    def __init__(self) -> None:
        self.records = {
            f"/isbn/{PINK_CAKE}.json": _real(f"isbn_{PINK_CAKE}"),
            "/works/OL29227890W.json": _real("works_OL29227890W"),
            "/authors/OL7106535A.json": _real("authors_OL7106535A"),
        }
        self.requests: list[str] = []
        self.user_agents: set[str] = set()
        self.fail_with: int | None = None

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request.url.path)
        self.user_agents.add(request.headers.get("user-agent", ""))
        if self.fail_with:
            return httpx2.Response(self.fail_with)
        record = self.records.get(request.url.path)
        return httpx2.Response(200, json=record) if record else httpx2.Response(404)

    def add_edition(self, isbn13: str, **changes) -> None:
        edition = copy.deepcopy(self.records[f"/isbn/{PINK_CAKE}.json"])
        edition.update({"isbn_13": [isbn13], "key": f"/books/OL{isbn13[-6:]}M", **changes})
        self.records[f"/isbn/{isbn13}.json"] = edition
