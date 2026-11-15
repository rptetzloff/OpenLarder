"""Buy links (buying.py) and counting their clicks (routers/go.py)."""

import pytest
from sqlalchemy import text

from openlarder import buying, shops

ISBN = "9780393541113"


@pytest.fixture
async def book(adb):
    work = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    edition = await adb.scalar(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:w, :i) RETURNING id"),
        {"w": work, "i": ISBN},
    )
    recipe = await adb.scalar(
        text("INSERT INTO recipes (source_id, title) VALUES (:w, 'Rhubarb Cake') RETURNING id"),
        {"w": work},
    )
    await adb.execute(
        text(
            "INSERT INTO recipe_locations (source_id, recipe_id, edition_id, page)"
            " VALUES (:w, :r, :e, '112')"
        ),
        {"w": work, "r": recipe, "e": edition},
    )
    return {"work": work, "edition": edition, "recipe": recipe}


async def _switch_on(adb, kind: str, key: str, column: str, value: str) -> None:
    """A shop as migration 0073 seeds it where its variable was set: its
    setting on its row, switched on, changed by nobody."""
    await adb.execute(
        text(
            f"UPDATE shops SET {column} = :value, enabled = true WHERE kind = :kind AND key = :key"
        ),
        {"value": value, "kind": kind, "key": key},
    )
    shops.reset()


# The shops' settings here are on their rows, as the migration seeds them
# from the variables they were in before the shops table (0073). Until the
# variables went (*Ray, 2026-11-13*) these fixtures set the variables
# themselves, and every address asserted below is as it was then: the
# links didn't change when the settings moved.
@pytest.fixture
async def affiliate(adb):
    await _switch_on(adb, "bookseller", "bookshop", "affiliate_id", "12345")


BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/140.0"}


async def test_no_links_until_the_affiliate_id_is_set(client, book) -> None:
    shown = (await client.get(f"/api/sources/{book['work']}")).json()
    assert shown["editions"][0]["buy"] == []
    response = await client.get(f"/go/bookshop/{book['edition']}", headers=BROWSER)
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"


async def test_a_book_and_its_recipes_link_to_bookshop(client, book, affiliate) -> None:
    edition = book["edition"]
    link = {
        "retailer": "bookshop",
        "label": "Bookshop.org",
        "url": f"/go/bookshop/{edition}",
        "note": None,
        "format": "print",
    }
    shown = (await client.get(f"/api/sources/{book['work']}")).json()
    assert shown["editions"][0]["buy"] == [link]
    recipe = (await client.get(f"/api/recipes/{book['recipe']}")).json()
    assert recipe["pages"][0]["buy"] == [link]


async def test_a_click_is_counted_and_sent_on(client, book, affiliate, adb) -> None:
    response = await client.get(
        f"/go/bookshop/{book['edition']}",
        params={"from": f"/recipes/{book['recipe']}?x=1"},
        headers=BROWSER,
    )
    assert response.status_code == 302
    assert response.headers["location"] == f"https://bookshop.org/a/12345/{ISBN}"
    assert response.headers["cache-control"] == "no-store"
    rows = (await adb.execute(text("SELECT retailer, page FROM purchase_clicks"))).all()
    # The path only: no query.
    assert [tuple(r) for r in rows] == [("bookshop", f"/recipes/{book['recipe']}")]


@pytest.mark.parametrize(
    "agent",
    [None, "Googlebot/2.1", "facebookexternalhit/1.1", "curl/8.4.0", "python-httpx/0.27"],
)
async def test_a_bot_is_sent_on_but_not_counted(client, book, affiliate, adb, agent) -> None:
    headers = {"User-Agent": agent} if agent else {"User-Agent": ""}
    response = await client.get(f"/go/bookshop/{book['edition']}", headers=headers)
    assert response.status_code == 302
    assert await adb.scalar(text("SELECT count(*) FROM purchase_clicks")) == 0


async def test_only_a_books_edition_with_an_isbn_has_links(client, book, affiliate, adb) -> None:
    await adb.execute(text("UPDATE editions SET isbn13 = NULL"))
    assert (await client.get(f"/go/bookshop/{book['edition']}", headers=BROWSER)).status_code == 404
    await adb.execute(text("UPDATE editions SET isbn13 = :i"), {"i": ISBN})
    await adb.execute(text("UPDATE sources SET kind = 'magazine'"))
    assert (await client.get(f"/go/bookshop/{book['edition']}", headers=BROWSER)).status_code == 404
    unknown = await client.get(f"/go/amazon/{book['edition']}", headers=BROWSER)
    assert unknown.status_code == 404


@pytest.mark.parametrize(
    ("asked", "referer", "page"),
    [
        ("/sources/1", None, "/sources/1"),
        (None, "https://openlarder.com/recipes/2?y=1", "/recipes/2"),
        ("//evil.example/x", None, None),
        ("https://evil.example/x", None, None),
        ("/" + "a" * 400, None, "/" + "a" * 299),
    ],
)
def test_the_page_is_a_path_on_this_site(asked, referer, page) -> None:
    assert buying.page_of(asked, referer) == page


# What a setting may look like (an id that's a number, a tag that's a tag, a
# deep link with {url}) was config.py's to refuse while the settings were
# variables. The administrator's form refuses the same now:
# test_shops_admin.py, test_what_cant_work_is_refused_and_says_why.


# More shops (Ray, 2026-11-09): Amazon by its tag; the rest by a network's
# deep-link template with {url} where the shop's address goes.

TEMPLATE = "https://click.example/deeplink?id=7&murl={url}"


@pytest.fixture
async def every_shop(adb):
    await _switch_on(adb, "bookseller", "bookshop", "affiliate_id", "12345")
    await _switch_on(adb, "bookseller", "amazon", "affiliate_id", "openlarder-20")
    for key in ("bn", "thriftbooks", "bookoutlet", "kobo"):
        await _switch_on(adb, "bookseller", key, "wrapper_template", TEMPLATE)


async def test_each_shop_set_shows_in_order(client, book, every_shop, adb) -> None:
    await adb.execute(
        text(
            "WITH a AS (INSERT INTO authors (name, name_key) VALUES ('Claire Ptak', 'claire ptak')"
            " RETURNING id) INSERT INTO source_credits (source_id, author_id, position,"
            " credited_as) SELECT :w, id, 1, 'Claire Ptak' FROM a"
        ),
        {"w": book["work"]},
    )
    buy = (await client.get(f"/api/sources/{book['work']}")).json()["editions"][0]["buy"]
    assert [b["label"] for b in buy] == [
        "Bookshop.org",
        "Barnes & Noble",
        "ThriftBooks",
        "Book Outlet",
        "Amazon",
        "Kobo",
    ]
    # Print first, then the ebook.
    assert [b["format"] for b in buy] == ["print"] * 5 + ["ebook"]
    # Amazon's programme asks for its own words beside its link.
    assert [b["note"] for b in buy if b["note"]] == [
        "As an Amazon Associate, OpenLarder earns from qualifying purchases."
    ]

    async def goes(shop):
        response = await client.get(f"/go/{shop}/{book['edition']}", headers=BROWSER)
        assert response.status_code == 302
        return response.headers["location"]

    assert await goes("amazon") == "https://www.amazon.com/dp/0393541118?tag=openlarder-20"
    assert await goes("bn") == (
        "https://click.example/deeplink?id=7&murl="
        "https%3A%2F%2Fwww.barnesandnoble.com%2Fw%2F%3Fean%3D9780393541113"
    )
    assert await goes("thriftbooks") == (
        "https://click.example/deeplink?id=7&murl="
        "https%3A%2F%2Fwww.thriftbooks.com%2Fbrowse%2F%3Fb.search%3D9780393541113"
    )
    assert await goes("bookoutlet") == (
        "https://click.example/deeplink?id=7&murl="
        "https%3A%2F%2Fbookoutlet.com%2Fsearch%3Fq%3D9780393541113"
    )
    # An ebook has its own ISBN: Kobo is searched by title and author.
    assert await goes("kobo") == (
        "https://click.example/deeplink?id=7&murl="
        "https%3A%2F%2Fwww.kobo.com%2Fus%2Fen%2Fsearch%3Fquery%3DPink%2520Cake%2520Claire%2520Ptak"
    )
    counted = await adb.scalar(text("SELECT count(DISTINCT retailer) FROM purchase_clicks"))
    assert counted == 5


def test_amazon_uses_isbn10_or_searches_a_979() -> None:
    assert buying.isbn10("9780393541113") == "0393541118"
    assert buying.isbn10("9780306406157") == "0306406152"
    assert buying.isbn10("9781861972712") == "1861972717"
    assert buying.isbn10("9780804429573") == "080442957X"
    assert buying.isbn10("9791032300824") is None
    amazon = shops.Shop(
        key="amazon",
        kind="bookseller",
        label="Amazon",
        builder="amazon",
        affiliate_id="openlarder-20",
        wrapper_template=None,
        product_template=None,
        format="print",
        earns="affiliate",
        note=None,
        enabled=True,
        position=4,
    )
    book = buying.Book(isbn13="9791032300824", title="X", author=None)
    assert shops.for_book(amazon, book) == (
        "https://www.amazon.com/s?k=9791032300824&i=stripbooks&tag=openlarder-20"
    )
