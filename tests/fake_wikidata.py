"""A fake Wikidata query service, answering from responses saved from the
real one (tests/data/wikidata, CC0 like all of Wikidata).

It reads which IDs a query asks about and answers with the saved rows for
those only, as the real service would; tests add rows for more items.
"""

import copy
import json
import re
from pathlib import Path
from urllib.parse import parse_qs

import httpx2

DATA = Path(__file__).parent / "data" / "wikidata"


def _rows(name: str) -> list[dict]:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))["results"]["bindings"]


def row(item: str, **values: str) -> dict:
    """A row as the service gives it: row("Q1", ol="OL1A", born="1950-01-01T00:00:00Z")."""
    out = {"item": {"type": "uri", "value": f"http://www.wikidata.org/entity/{item}"}}
    for name, value in values.items():
        out[name] = {"type": "literal", "value": value}
    return out


class FakeWikidata:
    def __init__(self) -> None:
        # Found by Open Library ID, and by Wikidata ID.
        self.by_ol = copy.deepcopy(_rows("by_open_library_id"))
        self.by_q = copy.deepcopy(_rows("by_wikidata_id"))
        self.queries: list[str] = []
        self.user_agents: set[str] = set()
        self.fail_with: int | None = None
        # Items citing a USDA NDB number (P1978): row("Q1", ndb="11282", label="onion").
        self.by_ndb: list[dict] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        query = parse_qs(request.content.decode())["query"][0]
        self.queries.append(query)
        self.user_agents.add(request.headers.get("user-agent", ""))
        if self.fail_with:
            return httpx2.Response(self.fail_with)
        if "P1978" in query:
            rows = self.by_ndb
        elif "VALUES ?ol" in query:
            asked = set(re.findall(r'"(OL[0-9]+A)"', query))
            rows = [r for r in self.by_ol if r.get("ol", {}).get("value") in asked]
        else:
            asked = set(re.findall(r"wd:(Q[0-9]+)", query))
            rows = [r for r in self.by_q if r["item"]["value"].rsplit("/", 1)[-1] in asked]
        return httpx2.Response(200, json={"head": {"vars": []}, "results": {"bindings": rows}})
