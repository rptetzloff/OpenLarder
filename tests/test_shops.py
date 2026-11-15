"""The shops table (migration 0073; shops.py): the booksellers and grocers
read from their rows, kept a minute. The environment variables their
settings used to be in aren't read any more: migration 0076 copied the last
of them onto the rows. *Ray, 2026-11-13.*"""

import importlib.util
import pathlib

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from openlarder import dumps, shops
from openlarder.config import Settings

ISBN = "9780393541113"
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/140.0"}
WRAPPER = "https://click.example/deeplink?id=7&murl={url}"


@pytest.fixture
async def book(adb):
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    edition = await adb.scalar(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:w, :i) RETURNING id"),
        {"w": work, "i": ISBN},
    )
    return {"work": work, "edition": edition}


async def _set(adb, kind: str, key: str, by=None, **columns) -> None:
    """Changes a shop's row, as an administrator will; by: who did."""
    columns = {**columns, "updated_by": by}
    await adb.execute(
        text(
            f"UPDATE shops SET {', '.join(f'{c} = :{c}' for c in columns)}"
            " WHERE kind = :kind AND key = :key"
        ),
        {**columns, "kind": kind, "key": key},
    )
    shops.reset()


async def _buy(client, book) -> list[str]:
    shown = (await client.get(f"/api/sources/{book['work']}")).json()
    return [b["retailer"] for b in shown["editions"][0]["buy"]]


async def _goes(client, path: str) -> str | None:
    response = await client.get(path, headers=BROWSER)
    return response.headers["location"] if response.status_code == 302 else None


async def test_the_shops_there_were_are_rows_in_their_order(adb) -> None:
    rows = (
        await adb.execute(
            text("SELECT kind, key, label, builder, format FROM shops ORDER BY kind, position")
        )
    ).all()
    assert [tuple(r) for r in rows] == [
        ("bookseller", "bookshop", "Bookshop.org", "bookshop", "print"),
        ("bookseller", "bn", "Barnes & Noble", "wrapped", "print"),
        ("bookseller", "thriftbooks", "ThriftBooks", "wrapped", "print"),
        ("bookseller", "bookoutlet", "Book Outlet", "wrapped", "print"),
        ("bookseller", "amazon", "Amazon", "amazon", "print"),
        ("bookseller", "kobo", "Kobo", "wrapped", "ebook"),
        ("grocer", "instacart", "Instacart", "wrapped", None),
        ("grocer", "amazon", "Amazon Fresh", "amazon", None),
        ("grocer", "walmart", "Walmart", "wrapped", None),
    ]
    # No variable is set where the tests' database was made: each is seeded
    # switched off, with no setting, and nobody's.
    blank = await adb.scalar(
        text(
            "SELECT count(*) FROM shops WHERE NOT enabled AND affiliate_id IS NULL"
            " AND wrapper_template IS NULL AND updated_by IS NULL"
        )
    )
    assert blank == 9


def _migration(name: str = "0073_shops"):
    path = pathlib.Path(__file__).parent.parent / "migrations" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"migration_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_copies_each_variable_that_is_set() -> None:
    rows = _migration().seeded(
        {
            "OPENLARDER_BOOKSHOP_AFFILIATE_ID": " 12345 ",
            "OPENLARDER_AMAZON_TAG": "openlarder-20",
            "OPENLARDER_KOBO_LINK": WRAPPER,
            "OPENLARDER_INSTACART_LINK": "",
        }
    )
    by = {(r["kind"], r["key"]): r for r in rows}
    assert (
        by["bookseller", "bookshop"]["affiliate_id"],
        by["bookseller", "bookshop"]["enabled"],
    ) == (
        "12345",
        True,
    )
    # The one tag is Amazon's for books and for groceries.
    assert by["bookseller", "amazon"]["affiliate_id"] == "openlarder-20"
    assert by["grocer", "amazon"]["affiliate_id"] == "openlarder-20"
    assert by["bookseller", "kobo"]["wrapper_template"] == WRAPPER
    # Not set, or set to nothing: there, and switched off.
    for unset in (("bookseller", "bn"), ("grocer", "instacart"), ("grocer", "walmart")):
        assert (by[unset]["enabled"], by[unset]["wrapper_template"]) == (False, None)
    assert sorted(r["position"] for r in rows if r["kind"] == "grocer") == [0, 1, 2]


async def test_a_bookseller_is_read_from_its_row(client, adb, book, people) -> None:
    assert await _buy(client, book) == []
    await people("ann", admin=True)
    ann = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'ann'"))
    await _set(adb, "bookseller", "bookshop", by=ann, affiliate_id="777", enabled=True)
    assert await _buy(client, book) == ["bookshop"]
    assert await _goes(client, f"/go/bookshop/{book['edition']}") == (
        f"https://bookshop.org/a/777/{ISBN}"
    )
    # Through a network's deep link, and in the order the rows say.
    await _set(adb, "bookseller", "bn", by=ann, wrapper_template=WRAPPER, enabled=True)
    await _set(adb, "bookseller", "bookshop", by=ann, position=9)
    assert await _buy(client, book) == ["bn", "bookshop"]
    assert await _goes(client, f"/go/bn/{book['edition']}") == (
        "https://click.example/deeplink?id=7&murl="
        "https%3A%2F%2Fwww.barnesandnoble.com%2Fw%2F%3Fean%3D9780393541113"
    )


async def test_switched_off_it_isnt_shown_or_followed(client, adb, book) -> None:
    await _set(adb, "bookseller", "bookshop", affiliate_id="777", enabled=True)
    assert await _buy(client, book) == ["bookshop"]
    await _set(adb, "bookseller", "bookshop", affiliate_id="777", enabled=False)
    assert await _buy(client, book) == []
    assert await _goes(client, f"/go/bookshop/{book['edition']}") is None
    # Switched on with nothing to earn by: a link that earns nothing isn't shown.
    await _set(adb, "bookseller", "bookshop", affiliate_id=None, enabled=True)
    assert await _buy(client, book) == []


# The variables go (migration 0076, then nothing reads them)

LAST = "0076_shops_last_of_the_variables"
EVERY_VARIABLE = {
    "OPENLARDER_BOOKSHOP_AFFILIATE_ID": " 12345 ",
    "OPENLARDER_AMAZON_TAG": "openlarder-20",
    "OPENLARDER_BARNES_NOBLE_LINK": WRAPPER,
    "OPENLARDER_THRIFTBOOKS_LINK": WRAPPER,
    "OPENLARDER_BOOKOUTLET_LINK": WRAPPER,
    "OPENLARDER_KOBO_LINK": WRAPPER,
    "OPENLARDER_INSTACART_LINK": WRAPPER,
    "OPENLARDER_WALMART_LINK": WRAPPER,
}


async def _copy(adb, environ) -> None:
    """Migration 0076's own statements, run here."""
    for statement, values in _migration(LAST).updates(environ):
        await adb.execute(text(statement), values)
    shops.reset()


async def _settings_of(adb) -> dict:
    rows = await adb.execute(
        text("SELECT kind, key, affiliate_id, wrapper_template, enabled FROM shops")
    )
    return {(r.kind, r.key): (r.affiliate_id or r.wrapper_template, r.enabled) for r in rows}


async def test_a_variable_set_since_the_table_came_is_copied_onto_its_shop(
    client, adb, book
) -> None:
    """What the app did for one release, made standing: a shop nobody has
    changed, with no setting, takes its variable's and is switched on."""
    assert await _buy(client, book) == []
    await _copy(adb, EVERY_VARIABLE)

    now = await _settings_of(adb)
    assert now["bookseller", "bookshop"] == ("12345", True)
    # The one tag is Amazon's for books and for groceries.
    assert now["bookseller", "amazon"] == ("openlarder-20", True)
    assert now["grocer", "amazon"] == ("openlarder-20", True)
    for shop in (
        ("bookseller", "bn"),
        ("bookseller", "thriftbooks"),
        ("bookseller", "bookoutlet"),
        ("bookseller", "kobo"),
        ("grocer", "instacart"),
        ("grocer", "walmart"),
    ):
        assert now[shop] == (WRAPPER, True), shop
    # Nobody's change still: the admin page goes on saying so.
    assert not await adb.scalar(text("SELECT count(*) FROM shops WHERE updated_by IS NOT NULL"))
    # And the links are the ones the variables gave.
    assert await _buy(client, book) == [
        "bookshop",
        "bn",
        "thriftbooks",
        "bookoutlet",
        "amazon",
        "kobo",
    ]
    assert await _goes(client, f"/go/bookshop/{book['edition']}") == (
        f"https://bookshop.org/a/12345/{ISBN}"
    )


async def test_a_shop_with_a_setting_or_somebodys_change_is_left_alone(adb, people) -> None:
    await people("ann", admin=True)
    ann = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'ann'"))
    # Its own setting, switched off since: the row wins, as it did.
    await _set(adb, "bookseller", "bookshop", affiliate_id="777", enabled=False)
    # Somebody emptied this one and switched it off: it stays as they left it.
    await _set(adb, "bookseller", "kobo", by=ann, wrapper_template=None, enabled=False)
    await _copy(adb, EVERY_VARIABLE)

    now = await _settings_of(adb)
    assert now["bookseller", "bookshop"] == ("777", False)
    assert now["bookseller", "kobo"] == (None, False)


async def test_a_variable_not_set_or_of_the_wrong_shape_copies_nothing(adb) -> None:
    before = await _settings_of(adb)
    await _copy(
        adb,
        {
            "OPENLARDER_BOOKSHOP_AFFILIATE_ID": "12345/../x",
            "OPENLARDER_AMAZON_TAG": "openlarder 20",
            "OPENLARDER_KOBO_LINK": "https://click.example/deeplink?id=7",
            "OPENLARDER_BOOKOUTLET_LINK": "http://click.example/?u={url}",
            "OPENLARDER_WALMART_LINK": "  ",
        },
    )
    assert await _settings_of(adb) == before
    assert _migration(LAST).updates({}) == []


async def test_the_variables_arent_read_any_more(client, adb, book, monkeypatch) -> None:
    """One left behind in Coolify does nothing, and one of the wrong shape
    doesn't stop the app starting, as it did while they were settings."""
    monkeypatch.setenv("OPENLARDER_BOOKSHOP_AFFILIATE_ID", "12345")
    monkeypatch.setenv("OPENLARDER_AMAZON_TAG", "not a tag!")
    settings = Settings()
    for gone in (
        "bookshop_affiliate_id",
        "amazon_tag",
        "barnes_noble_link",
        "thriftbooks_link",
        "bookoutlet_link",
        "kobo_link",
        "instacart_link",
        "walmart_link",
    ):
        assert not hasattr(settings, gone), gone
    # Nor does the shops' own module ask for the settings at all.
    assert not hasattr(shops, "get_settings")
    # A shop nobody has changed, with no setting of its own, shows nothing.
    assert await _buy(client, book) == []
    assert await _goes(client, f"/go/bookshop/{book['edition']}") is None


async def test_the_rows_are_kept_a_minute(client, adb, book, monkeypatch) -> None:
    await _set(adb, "bookseller", "bookshop", affiliate_id="777", enabled=True)
    assert await _buy(client, book) == ["bookshop"]
    # Changed behind the app's back, as by another worker: not seen yet.
    await adb.execute(
        text("UPDATE shops SET enabled = false WHERE kind = 'bookseller' AND key = 'bookshop'")
    )
    assert await _buy(client, book) == ["bookshop"]
    now = shops.time.monotonic()
    monkeypatch.setattr(shops.time, "monotonic", lambda: now + shops.TTL - 1)
    assert await _buy(client, book) == ["bookshop"]
    monkeypatch.setattr(shops.time, "monotonic", lambda: now + shops.TTL + 1)
    assert await _buy(client, book) == []


async def test_a_new_bookseller_needs_only_a_row(client, adb, book) -> None:
    await adb.execute(
        text(
            "WITH a AS (INSERT INTO authors (name, name_key) VALUES ('Claire Ptak', 'claire ptak')"
            " RETURNING id) INSERT INTO source_credits (source_id, author_id, position,"
            " credited_as) SELECT :w, id, 1, 'Claire Ptak' FROM a"
        ),
        {"w": book["work"]},
    )
    await adb.execute(
        text(
            "INSERT INTO shops (key, kind, label, builder, product_template, format, earns,"
            " enabled, position) VALUES ('corner', 'bookseller', 'The Corner Shop', 'template',"
            " 'https://corner.example/find?isbn={isbn13}&short={isbn10}&t={title}&by={author}',"
            " 'print', 'none', true, -1)"
        )
    )
    shops.reset()
    shown = (await client.get(f"/api/sources/{book['work']}")).json()
    assert [(b["retailer"], b["label"]) for b in shown["editions"][0]["buy"]] == [
        ("corner", "The Corner Shop")
    ]
    # Each part encoded as it's put in.
    assert await _goes(client, f"/go/corner/{book['edition']}") == (
        "https://corner.example/find?isbn=9780393541113&short=0393541118"
        "&t=Pink%20Cake&by=Claire%20Ptak"
    )
    # People may put it in their order of shops, as any other.
    assert await shops.find(adb, "bookseller", "corner") is not None


async def test_a_template_asking_for_an_isbn10_a_book_hasnt_gives_no_link(adb) -> None:
    corner = shops.Shop(
        key="corner",
        kind="bookseller",
        label="The Corner Shop",
        builder="template",
        affiliate_id=None,
        wrapper_template=None,
        product_template="https://corner.example/{isbn10}",
        format="print",
        earns="none",
        note=None,
        enabled=True,
        position=0,
    )
    assert shops.for_book(corner, shops.Book("9780393541113", "Pink Cake", None)) == (
        "https://corner.example/0393541118"
    )
    # A 979 ISBN has no 10-digit form.
    assert shops.for_book(corner, shops.Book("9791032300824", "X", None)) is None


async def test_a_grocer_is_read_from_its_row(client, adb) -> None:
    onion = str(
        await adb.scalar(
            text(
                "INSERT INTO ingredients (name, match_key) VALUES ('Red Onion', 'red onion')"
                " RETURNING id"
            )
        )
    )
    assert (await client.get("/api/grocers")).json() == []
    await _set(adb, "grocer", "walmart", wrapper_template=WRAPPER, enabled=True)
    await _set(adb, "grocer", "amazon", affiliate_id="openlarder-20", enabled=True)
    assert [g["key"] for g in (await client.get("/api/grocers")).json()] == ["amazon", "walmart"]
    assert await _goes(client, f"/go/grocer/walmart/{onion}") == (
        "https://click.example/deeplink?id=7&murl="
        "https%3A%2F%2Fwww.walmart.com%2Fsearch%3Fq%3DRed%2BOnion"
    )
    assert await _goes(client, f"/go/grocer/amazon/{onion}") == (
        "https://www.amazon.com/s?k=Red+Onion&i=amazonfresh&tag=openlarder-20"
    )
    assert await _goes(client, f"/go/grocer/instacart/{onion}") is None


async def test_amazon_is_a_bookseller_and_a_grocer_and_each_once(adb) -> None:
    """The key is unique among a kind: /go/amazon/… and /go/grocer/amazon/…
    are both on the web already."""
    kinds = await adb.scalars(text("SELECT kind FROM shops WHERE key = 'amazon' ORDER BY kind"))
    assert list(kinds) == ["bookseller", "grocer"]
    with pytest.raises(IntegrityError):
        async with adb.begin_nested():
            await adb.execute(
                text(
                    "INSERT INTO shops (key, kind, label, builder)"
                    " VALUES ('amazon', 'grocer', 'Another', 'template')"
                )
            )


def test_shops_are_in_no_data_dump() -> None:
    assert "shops" not in dumps.COLUMNS
