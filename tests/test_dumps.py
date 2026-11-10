"""Weekly ODbL data dumps (dumps.py, routers/dumps.py, s3.py)."""

import csv
import io
import json
import zipfile

import httpx2
import pytest
from pydantic import ValidationError
from sqlalchemy import text

from fake_broker import _settings
from openlarder import dumps
from openlarder.config import Settings
from openlarder.main import app
from openlarder.routers.dumps import dumps_transport

STORE = {
    "dumps_endpoint": "https://account.r2.cloudflarestorage.com",
    "dumps_bucket": "openlarder-data",
    "dumps_access_key": "AKIDEXAMPLE",
    "dumps_secret_key": "secret",
    "dumps_public_url": "https://data.openlarder.com",
}


class FakeStore:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.auth: list[str] = []
        self.fail = False

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        if self.fail:
            return httpx2.Response(403, text="<Error>AccessDenied</Error>")
        assert request.method == "PUT"
        self.auth.append(request.headers["authorization"])
        self.files[request.url.path] = request.content
        return httpx2.Response(200)


@pytest.fixture
def store(configure):
    configure(_settings(**STORE))
    fake = FakeStore()
    app.dependency_overrides[dumps_transport] = lambda: httpx2.MockTransport(fake.handle)
    return fake


@pytest.fixture
async def catalog(people, adb):
    """A published book with a recipe, and everything that mustn't get out:
    a private collection, a book waiting for review, a recipe waiting in the
    published book."""
    mo, con, ann = (
        await people("mo", role="moderator"),
        await people("con", role="contributor"),
        await people("ann"),
    )
    book = (
        await mo.post(
            "/api/sources/manual", json={"title": "Plenty", "authors": ["Yotam Ottolenghi"]}
        )
    ).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    recipe = (
        await mo.post(
            f"/api/sources/{book}/recipes",
            json={
                "title": "Shakshuka",
                "editions": [{"edition_id": edition, "page": "12"}],
                "ingredients": ["eggs", "tomatoes or passata"],
            },
        )
    ).json()["id"]
    box = (
        await ann.post("/api/sources/family", json={"title": "Secret Box", "acknowledged": True})
    ).json()["id"]
    await ann.post(
        f"/api/sources/{box}/recipes", json={"title": "Secret Stew", "ingredients": ["Moonsalt"]}
    )
    await con.post(
        "/api/sources/manual", json={"title": "Pending Larder", "authors": ["Penny Pending"]}
    )
    await con.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Waiting Pie",
            "editions": [{"edition_id": edition}],
            "ingredients": ["Dustberry"],
        },
    )
    return {"book": book, "recipe": recipe, "edition": edition}


HIDDEN = (
    "Secret Box",
    "Secret Stew",
    "Moonsalt",
    "Pending Larder",
    "Penny Pending",
    "Waiting Pie",
    "Dustberry",
)


def _unzip(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name).decode() for name in archive.namelist()}


async def test_an_admin_builds_one_and_anyone_finds_it(store, catalog, people, client) -> None:
    assert (await client.get("/api/dumps")).json()["latest"] is None
    mo = await people("mo2", role="moderator")
    assert (await mo.post("/api/admin/dumps")).status_code == 403
    admin = await people("ad", admin=True)
    r = await admin.post("/api/admin/dumps")
    assert r.status_code == 200, r.text
    built = r.json()
    assert built["csv_url"].startswith("https://data.openlarder.com/dumps/openlarder-")
    assert built["counts"]["recipes"] == 1 and built["counts"]["sources"] == 1
    paths = sorted(store.files)
    assert [p.split("-")[-1] for p in paths] == ["csv.zip", "jsonl.zip"]
    assert all(p.startswith("/openlarder-data/dumps/") for p in paths)
    assert all(a.startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/") for a in store.auth)
    listed = (await client.get("/api/dumps")).json()
    assert listed["available"] and listed["latest"]["json_url"] == built["json_url"]
    assert "ODbL" in listed["attribution"]


async def test_the_files_hold_the_public_catalog_only(store, catalog, people) -> None:
    admin = await people("ad", admin=True)
    await admin.post("/api/admin/dumps")
    csv_zip, json_zip = (store.files[p] for p in sorted(store.files))
    tables = _unzip(csv_zip)
    assert "Open Database License" in tables["README.txt"]
    assert dumps.ATTRIBUTION in tables["README.txt"]
    recipes = list(csv.DictReader(io.StringIO(tables["recipes.csv"])))
    assert [r["title"] for r in recipes] == ["Shakshuka"]
    lines = list(csv.DictReader(io.StringIO(tables["recipe_ingredients.csv"])))
    assert [line["original_text"] for line in lines] == ["eggs", "tomatoes or passata"]
    pages = list(csv.DictReader(io.StringIO(tables["recipe_locations.csv"])))
    assert [p["page"] for p in pages] == ["12"]
    everything = "".join(tables.values()) + "".join(_unzip(json_zip).values())
    assert not [h for h in HIDDEN if h in everything]
    # Nothing about accounts: no column names a person.
    for name, content in tables.items():
        if name.endswith(".csv"):
            header = content.splitlines()[0].split(",")
            for column in ("created_by", "owner_id", "reviewed_by", "proposed_by", "user_id"):
                assert column not in header, (name, column)


async def test_the_json_nests_each_recipe(store, catalog, people) -> None:
    admin = await people("ad", admin=True)
    await admin.post("/api/admin/dumps")
    files = _unzip(store.files[sorted(store.files)[1]])
    [recipe] = [json.loads(line) for line in files["recipes.jsonl"].splitlines()]
    assert recipe["title"] == "Shakshuka" and recipe["source_id"] == catalog["book"]
    [place] = recipe["places"]
    assert (place["edition_id"], place["page"]) == (catalog["edition"], "12")
    assert [i["text"] for i in recipe["ingredients"]] == ["eggs", "tomatoes or passata"]
    assert [o["name"] for o in recipe["ingredients"][1]["options"]] == ["tomatoes", "passata"]
    [source] = [json.loads(line) for line in files["sources.jsonl"].splitlines()]
    assert [c["credited_as"] for c in source["credits"]] == ["Yotam Ottolenghi"]
    assert source["editions"][0]["id"] == catalog["edition"]


async def test_a_failed_upload_records_nothing(store, catalog, people, client) -> None:
    store.fail = True
    admin = await people("ad", admin=True)
    r = await admin.post("/api/admin/dumps")
    assert r.status_code == 502 and "403" in r.json()["detail"]
    assert (await client.get("/api/dumps")).json()["latest"] is None


async def test_without_settings_there_are_none(client, people) -> None:
    assert (await client.get("/api/dumps")).json()["available"] is False
    admin = await people("ad", admin=True)
    assert (await admin.post("/api/admin/dumps")).status_code == 409


def test_half_the_settings_refuse_to_start() -> None:
    with pytest.raises(ValidationError, match="OPENLARDER_DUMPS_SECRET_KEY"):
        Settings(**{k: v for k, v in STORE.items() if k != "dumps_secret_key"})
    with pytest.raises(ValidationError, match="web address"):
        Settings(**{**STORE, "dumps_public_url": "data.openlarder.com"})
    assert Settings(**STORE).dumps_configured


async def test_one_is_due_a_week_after_the_last(adb) -> None:
    assert await dumps.due(adb)
    await adb.execute(
        text(
            "INSERT INTO dumps (csv_key, csv_bytes, json_key, json_bytes, counts, built_at)"
            " VALUES ('a', 1, 'b', 1, '{}', now() - interval '6 days')"
        )
    )
    assert not await dumps.due(adb)
    await adb.execute(text("UPDATE dumps SET built_at = now() - interval '7 days 1 minute'"))
    assert await dumps.due(adb)
