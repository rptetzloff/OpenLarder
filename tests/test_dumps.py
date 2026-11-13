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
    assert "ODbL" in listed["attribution"] and listed["keep_days"] == 365


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


async def test_a_rating_is_the_average_and_how_many_never_who(store, catalog, people, adb) -> None:
    """As a recipe's page shows it. The ratings themselves say who gave
    what, and no dump does."""
    ann, bo = await people("ann2"), await people("bo")
    url = f"/api/recipes/{catalog['recipe']}/rating"
    assert (await ann.put(url, json={"spoons": 5})).status_code == 200
    assert (await bo.put(url, json={"spoons": 4})).status_code == 200
    # A private recipe's rating, by the one person who can see it.
    stew = await adb.scalar(text("SELECT id FROM recipes WHERE title = 'Secret Stew'"))
    owner = await adb.scalar(
        text(
            "SELECT s.owner_id FROM sources s JOIN recipes r ON r.source_id = s.id WHERE r.id = :r"
        ),
        {"r": stew},
    )
    await adb.execute(
        text("INSERT INTO recipe_ratings (user_id, recipe_id, spoons) VALUES (:u, :r, 1)"),
        {"u": owner, "r": stew},
    )
    admin = await people("ad", admin=True)
    built = await admin.post("/api/admin/dumps")
    assert built.json()["counts"]["recipe_ratings"] == 1
    csv_zip, json_zip = (_unzip(store.files[p]) for p in sorted(store.files))
    assert list(csv.DictReader(io.StringIO(csv_zip["recipe_ratings.csv"]))) == [
        {"recipe_id": catalog["recipe"], "spoons": "4.5", "ratings": "2"}
    ]
    [recipe] = [json.loads(line) for line in json_zip["recipes.jsonl"].splitlines()]
    assert (recipe["spoons"], recipe["ratings"]) == (4.5, 2)
    assert "recipe_ratings" in csv_zip["README.txt"] and "rating" in json_zip["README.txt"]
    # Nobody who rated is anywhere in either file.
    raters = [str(u) for u in await adb.scalars(text("SELECT user_id FROM recipe_ratings"))]
    assert len(raters) == 3
    everything = "".join(csv_zip.values()) + "".join(json_zip.values())
    assert not [u for u in raters if u in everything]
    assert str(stew) not in everything


async def test_an_unrated_recipe_says_so(store, catalog, people) -> None:
    admin = await people("ad", admin=True)
    await admin.post("/api/admin/dumps")
    csv_zip, json_zip = (_unzip(store.files[p]) for p in sorted(store.files))
    assert csv_zip["recipe_ratings.csv"].splitlines() == ["recipe_id,spoons,ratings"]
    [recipe] = [json.loads(line) for line in json_zip["recipes.jsonl"].splitlines()]
    assert (recipe["spoons"], recipe["ratings"]) == (None, 0)


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


async def test_dumps_older_than_a_year_are_deleted(store, adb, configure) -> None:
    from openlarder.models import Dump

    configure(_settings(**STORE))
    settings = Settings(**STORE)
    for age, stamp in ((400, "old"), (200, "kept"), (1, "new")):
        adb.add(
            Dump(
                csv_key=f"dumps/{stamp}-csv.zip",
                csv_bytes=1,
                json_key=f"dumps/{stamp}-jsonl.zip",
                json_bytes=1,
                counts={},
            )
        )
        await adb.flush()
        await adb.execute(
            text(
                "UPDATE dumps SET built_at = now() - make_interval(days => :d) WHERE csv_key = :k"
            ),
            {"d": age, "k": f"dumps/{stamp}-csv.zip"},
        )
    deleted = []
    store.handle = lambda request: (
        deleted.append((request.method, request.url.path)),
        httpx2.Response(204),
    )[1]
    gone = await dumps.prune(adb, settings, httpx2.MockTransport(store.handle))
    assert gone == 1
    assert deleted == [
        ("DELETE", "/openlarder-data/dumps/old-csv.zip"),
        ("DELETE", "/openlarder-data/dumps/old-jsonl.zip"),
    ]
    left = set(await adb.scalars(text("SELECT csv_key FROM dumps")))
    assert left == {"dumps/kept-csv.zip", "dumps/new-csv.zip"}


async def test_the_newest_is_kept_however_old(store, adb) -> None:
    from openlarder.models import Dump

    adb.add(Dump(csv_key="a", csv_bytes=1, json_key="b", json_bytes=1, counts={}))
    await adb.flush()
    await adb.execute(text("UPDATE dumps SET built_at = now() - interval '800 days'"))
    assert (
        await dumps.prune(
            adb, Settings(**STORE), httpx2.MockTransport(lambda r: httpx2.Response(204))
        )
        == 0
    )


async def test_a_failed_delete_keeps_the_dump_listed(store, adb) -> None:
    from openlarder import s3
    from openlarder.models import Dump

    for age in (400, 1):
        adb.add(Dump(csv_key=f"k{age}", csv_bytes=1, json_key=f"j{age}", json_bytes=1, counts={}))
        await adb.flush()
        await adb.execute(
            text(
                "UPDATE dumps SET built_at = now() - make_interval(days => :d) WHERE csv_key = :k"
            ),
            {"d": age, "k": f"k{age}"},
        )
    with pytest.raises(s3.UploadFailed):
        await dumps.prune(
            adb, Settings(**STORE), httpx2.MockTransport(lambda r: httpx2.Response(403))
        )
    assert await adb.scalar(text("SELECT count(*) FROM dumps")) == 2


def test_keeping_is_a_setting() -> None:
    assert Settings(**STORE).dumps_keep_days == 365
    assert Settings(**STORE, dumps_keep_days=90).dumps_keep_days == 90
    with pytest.raises(ValidationError):
        Settings(**STORE, dumps_keep_days=1)
