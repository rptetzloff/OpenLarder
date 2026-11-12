"""The pages the server fills in before the browser does (pages.py): a
recipe's and a source's get their own head, an id that names nothing is a
404, and nothing of a record someone signed out can't see is ever written.
*Ray's spec, 2026-11-11.*"""

import re
import uuid

import pytest
from sqlalchemy import text

from fake_broker import _settings, _sign_in, make_admins
from openlarder import pages
from openlarder.main import spa_response

E = uuid.uuid4()
GENERIC = "<title>OpenLarder</title>"


@pytest.fixture
async def admin(client, broker, adb):
    await _sign_in(client, broker)
    await adb.execute(make_admins())
    return client


async def _book(admin, title="Against All Grain", authors=("Walker, Danielle (Chef)",)):
    added = await admin.post("/api/sources/manual", json={"title": title, "authors": list(authors)})
    assert added.status_code == 200, added.text
    return added.json()["id"]


async def _recipe(admin, adb, book, title="Banana Bread", page="190", ingredients=("Egg",)):
    edition = await adb.scalar(
        text("SELECT id FROM editions WHERE source_id = :s LIMIT 1"), {"s": uuid.UUID(book)}
    )
    made = await admin.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": title,
            "editions": [{"edition_id": str(edition), "page": page}],
            "ingredients": list(ingredients),
        },
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


def _tag(page: str, pattern: str) -> list[str]:
    return re.findall(pattern, page)


def _content(page: str, key: str) -> list[str]:
    """Every content of the <meta> named or propertied so: one, if nothing
    was added twice."""
    return re.findall(rf'<meta (?:name|property)="{re.escape(key)}" content="([^"]*)" />', page)


# A recipe's page


async def test_a_recipes_page_has_its_own_head(admin, adb, client) -> None:
    book = await _book(admin)
    recipe = await _recipe(admin, adb, book, ingredients=("Egg", "Almond Flour", "Banana", "Honey"))
    response = await client.get(f"/recipes/{recipe}")
    assert response.status_code == 200
    # index.html, still: the SPA mounts as before, and is asked for again
    # after a deploy.
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"].startswith("text/html")
    page = response.text
    assert _tag(page, r"<title>(.*?)</title>") == ["Banana Bread · Against All Grain · OpenLarder"]
    said = (
        "Banana Bread is on page 190 of Against All Grain by Danielle Walker."
        " Ingredients: Egg, Almond Flour, Banana, Honey."
    )
    # In place of index.html's own tags, not beside them.
    assert _content(page, "description") == [said]
    assert _content(page, "og:description") == [said]
    assert _content(page, "og:title") == ["Banana Bread · Against All Grain · OpenLarder"]
    assert _content(page, "og:url") == [f"http://testserver/recipes/{recipe}"]
    assert _content(page, "og:type") == ["article"]
    assert _tag(page, r'<link rel="canonical" href="([^"]*)" />') == [
        f"http://testserver/recipes/{recipe}"
    ]
    assert _content(page, "robots") == []
    # The site's card image stays: no cover is OpenLarder's own to show.
    assert _content(page, "og:image") == ["https://openlarder.com/og-image.png"]


async def test_the_address_is_the_sites_public_one(admin, adb, client, configure) -> None:
    book = await _book(admin)
    recipe = await _recipe(admin, adb, book)
    settings = _settings()
    configure(settings.model_copy(update={"public_url": "https://openlarder.com"}))
    page = (await client.get(f"/recipes/{recipe}")).text
    assert _content(page, "og:url") == [f"https://openlarder.com/recipes/{recipe}"]


async def test_what_a_record_says_is_escaped(admin, adb, client) -> None:
    book = await _book(admin, title='Cakes & "Bakes"', authors=())
    recipe = await _recipe(admin, adb, book, title="<script>alert(1)</script> Pie")
    page = (await client.get(f"/recipes/{recipe}")).text
    assert "<script>alert(1)" not in page
    assert _tag(page, r"<title>(.*?)</title>") == [
        "&lt;script&gt;alert(1)&lt;/script&gt; Pie · Cakes &amp; &quot;Bakes&quot; · OpenLarder"
    ]
    assert _content(page, "description") == [
        "&lt;script&gt;alert(1)&lt;/script&gt; Pie is on page 190 of"
        " Cakes &amp; &quot;Bakes&quot;. Ingredients: Egg."
    ]


async def test_a_description_stays_under_160_characters(admin, adb, client) -> None:
    book = await _book(admin, authors=("Danielle Walker", "Simone Miller", "Rachael Bryant"))
    names = [f"Ingredient Number {n}" for n in range(1, 13)]
    recipe = await _recipe(admin, adb, book, ingredients=names)
    said = _content((await client.get(f"/recipes/{recipe}")).text, "description")[0]
    assert len(said) < 160
    # As many ingredients as fit, then how many more.
    assert said == (
        "Banana Bread is on page 190 of Against All Grain by Danielle Walker, Simone Miller"
        " and Rachael Bryant. Ingredients: Ingredient Number 1, and 11 more."
    )
    # A title too long for anything else is cut, not dropped.
    long = await _recipe(admin, adb, book, title="Very " * 38 + "Long Cake", page="2")
    said = _content((await client.get(f"/recipes/{long}")).text, "description")[0]
    assert len(said) < 160 and said.endswith("…")


async def test_where_a_recipe_is_reads_by_its_kind_of_source(admin, client) -> None:
    async def made(path, source, recipe):
        added = await admin.post(path, json=source)
        assert added.status_code == 200, added.text
        new = await admin.post(f"/api/sources/{added.json()['id']}/recipes", json=recipe)
        assert new.status_code == 201, new.text
        page = (await client.get(f"/recipes/{new.json()['id']}")).text
        return _content(page, "description")[0]

    assert (
        await made(
            "/api/sources/websites",
            {"address": "https://example.com/", "name": "Example Kitchen"},
            {
                "title": "Rhubarb Galette",
                "web_address": "https://example.com/rhubarb-galette",
                "ingredients": ["Rhubarb"],
            },
        )
        == "Rhubarb Galette is from Example Kitchen. Ingredients: Rhubarb."
    )
    assert (
        await made(
            "/api/sources/periodicals",
            {"kind": "magazine", "title": "Kitchen Monthly"},
            {"title": "Plum Torte", "issue": "2024-05-01", "issue_page": "42", "ingredients": []},
        )
        == "Plum Torte is in Kitchen Monthly, May 1, 2024, page 42."
    )
    assert (
        await made(
            "/api/sources/shows",
            {"kind": "tv_show", "title": "Salt and Time"},
            {
                "title": "Buttermilk Chicken",
                "episode": {"season": 1, "number": 2, "title": "Salt", "at": "12:34"},
                "ingredients": ["Chicken"],
            },
        )
        == "Buttermilk Chicken is from Salt and Time, Season 1, episode 2, “Salt”."
        " Ingredients: Chicken."
    )


# A source's page


async def test_a_sources_page_has_its_own_head(admin, adb, client) -> None:
    book = await _book(admin)
    await _recipe(admin, adb, book)
    await _recipe(admin, adb, book, title="Granola", page="12")
    page = (await client.get(f"/sources/{book}")).text
    assert _tag(page, r"<title>(.*?)</title>") == ["Against All Grain · OpenLarder"]
    said = (
        "Against All Grain, a book by Danielle Walker. 2 recipes indexed,"
        " each with where to find it and its ingredients."
    )
    assert _content(page, "description") == [said]
    assert _content(page, "og:description") == [said]
    assert _content(page, "og:type") == ["book"]
    assert _content(page, "og:url") == [f"http://testserver/sources/{book}"]
    empty = await _book(admin, title="Plenty", authors=())
    page = (await client.get(f"/sources/{empty}")).text
    assert _content(page, "description") == ["Plenty, a book. No recipes indexed yet."]


# The body, before the SPA draws it


def _body(page: str) -> str:
    """What's where the SPA mounts."""
    found = re.search(r'<div id="app">(.*?)</div>\s*<script type="module"', page, re.DOTALL)
    assert found, page
    return found.group(1)


async def test_a_recipes_page_says_what_it_shows(admin, adb, client) -> None:
    book = await _book(admin, authors=("Walker, Danielle (Chef)", "Simone Miller"))
    blend = await _recipe(
        admin, adb, book, title="Biscuit Blend", page="14", ingredients=("Flour",)
    )
    recipe = await _recipe(
        admin,
        adb,
        book,
        ingredients=("Egg", "Butter or Coconut Oil", "Biscuit Blend (p. 14)"),
    )
    shown = (await client.get(f"/api/recipes/{recipe}")).json()
    ids = {
        o["name"]: o["ingredient"]["id"]
        for line in shown["lines"]
        for o in line["options"]
        if o["ingredient"]
    }
    authors = {c["name"]: c["author_id"] for c in shown["source"]["credits"]}
    assert _body((await client.get(f"/recipes/{recipe}")).text) == (
        '<main><article class="wide">'
        '<nav aria-label="Breadcrumb"><a href="/sources">Sources</a> / '
        f'<a href="/sources/{book}">Against All Grain</a> / Banana Bread</nav>'
        "<h1>Banana Bread</h1>"
        f'<p>Page 190 of <a href="/sources/{book}">Against All Grain</a> by '
        f'<a href="/authors/{authors["Danielle Walker"]}">Danielle Walker</a> and '
        f'<a href="/authors/{authors["Simone Miller"]}">Simone Miller</a>.</p>'
        "<h2>Ingredients</h2><ul>"
        f'<li><a href="/ingredients/{ids["Egg"]}">Egg</a></li>'
        f'<li><a href="/ingredients/{ids["Butter"]}">Butter</a> or '
        f'<a href="/ingredients/{ids["Coconut Oil"]}">Coconut Oil</a></li>'
        f'<li><a href="/recipes/{blend}">Biscuit Blend</a> (p. 14)</li>'
        "</ul></article></main>"
    )


async def test_a_sources_page_lists_its_recipes(admin, adb, client, monkeypatch) -> None:
    book = await _book(admin)
    bread = await _recipe(admin, adb, book)
    granola = await _recipe(admin, adb, book, title="Granola", page="12")
    await _recipe(admin, adb, book, title="Waffles", page="20")
    author = (await client.get(f"/api/sources/{book}")).json()["credits"][0]["author_id"]
    head = (
        '<main><article class="wide">'
        '<nav aria-label="Breadcrumb"><a href="/sources">Sources</a> / Against All Grain</nav>'
        "<h1>Against All Grain</h1>"
        f'<p>A book by <a href="/authors/{author}">Danielle Walker</a>.</p>'
        "<h2>Recipes</h2><ul>"
        f'<li><a href="/recipes/{bread}">Banana Bread</a>, page 190</li>'
        f'<li><a href="/recipes/{granola}">Granola</a>, page 12</li>'
    )
    body = _body((await client.get(f"/sources/{book}")).text)
    assert body.startswith(head) and body.endswith("page 20</li></ul></article></main>")
    # Past the cap, the rest are a link away: the page itself, which has them.
    monkeypatch.setattr(pages, "RECIPES_LISTED", 2)
    assert _body((await client.get(f"/sources/{book}")).text) == (
        f'{head}</ul><p><a href="/sources/{book}">All 3 recipes</a></p></article></main>'
    )


async def test_a_summary_is_escaped(admin, adb, client) -> None:
    book = await _book(admin, title='Cakes & "Bakes"', authors=("<b>Ann</b>",))
    recipe = await _recipe(
        admin, adb, book, title="<script>alert(1)</script> Pie", ingredients=("<i>Egg</i>",)
    )
    for path in (f"/recipes/{recipe}", f"/sources/{book}"):
        body = _body((await client.get(path)).text)
        assert "<script>" not in body and "<b>" not in body and "<i>" not in body, path
        assert "&lt;script&gt;alert(1)&lt;/script&gt; Pie" in body
        assert "Cakes &amp; &quot;Bakes&quot;" in body


async def test_a_page_with_no_record_to_show_has_no_summary(people, client) -> None:
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Secret Box", "acknowledged": True})
    ).json()["id"]
    for asking in (client, ann):
        for path in (f"/sources/{box}", f"/recipes/{uuid.uuid4()}"):
            assert _body((await asking.get(path)).text) == "", path


# What isn't there, and what isn't for everyone


async def test_an_id_that_names_nothing_is_a_404(client) -> None:
    for path in (f"/recipes/{uuid.uuid4()}", f"/sources/{uuid.uuid4()}"):
        response = await client.get(path)
        assert response.status_code == 404, path
        # Still the page the SPA mounts in, to say "not found" itself.
        assert '<div id="app"></div>' in response.text and GENERIC in response.text
        assert _content(response.text, "robots") == ["noindex"]
        assert _content(response.text, "og:url") == []
        assert response.headers["cache-control"] == "no-cache"


SECRETS = ("Secret Box", "Secret Stew", "Zanzibar Moonsalt")


@pytest.mark.parametrize("who", ["nobody", "bob", "admin", "ann"])
async def test_a_private_record_is_never_written_into_its_page(people, client, who) -> None:
    """Whoever asks, its owner included: the page is built for someone
    signed out, and the owner's browser fills it in."""
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Secret Box", "acknowledged": True})
    ).json()["id"]
    stew = (
        await ann.post(
            f"/api/sources/{box}/recipes",
            json={"title": "Secret Stew", "ingredients": ["Zanzibar Moonsalt"]},
        )
    ).json()["id"]
    # It is there: its owner's API answer has it.
    assert (await ann.get(f"/api/recipes/{stew}")).json()["title"] == "Secret Stew"
    asking = {"nobody": client, "ann": ann}.get(who) or await people(who, admin=who == "admin")
    for path in (f"/recipes/{stew}", f"/sources/{box}"):
        response = await asking.get(path)
        # Not a 404: it's there for its owner, whose browser draws it.
        assert response.status_code == 200, path
        assert not [s for s in SECRETS if s in response.text], path
        assert GENERIC in response.text
        assert _content(response.text, "robots") == ["noindex"]
        assert _content(response.text, "og:url") == []


async def test_a_record_waiting_for_review_is_never_written_either(admin, adb, client) -> None:
    book = await _book(admin, title="Waiting Book")
    recipe = await _recipe(admin, adb, book, title="Waiting Pie")
    shown = await _recipe(admin, adb, book, title="Shown Pie", page="3")
    await adb.execute(
        text("UPDATE recipes SET review = 'pending' WHERE id = :r"), {"r": uuid.UUID(recipe)}
    )
    response = await client.get(f"/recipes/{recipe}")
    assert response.status_code == 200
    assert "Waiting Pie" not in response.text and "Waiting Book" not in response.text
    assert _content(response.text, "robots") == ["noindex"]
    # Its book's page counts only what's published.
    assert "1 recipe indexed" in (await client.get(f"/sources/{book}")).text
    await adb.execute(
        text("UPDATE sources SET review = 'pending' WHERE id = :s"), {"s": uuid.UUID(book)}
    )
    for path in (f"/sources/{book}", f"/recipes/{shown}"):
        response = await client.get(path)
        assert response.status_code == 200
        assert "Waiting Book" not in response.text and "Shown Pie" not in response.text
        assert _content(response.text, "robots") == ["noindex"]


async def _merged(adb, gone, kept, undone=False):
    await adb.execute(
        text(
            "INSERT INTO book_merges (gone_id, gone_title, kept_id, saved, undone_at)"
            " VALUES (:g, 'Gone', :k, '{}', CASE WHEN :u THEN now() END)"
        ),
        {"g": gone, "k": uuid.UUID(str(kept)), "u": undone},
    )


async def test_a_merged_sources_address_goes_to_the_one_kept(admin, adb, client, people) -> None:
    kept = await _book(admin, title="Kept")
    gone, earlier = uuid.uuid4(), uuid.uuid4()
    await _merged(adb, gone, kept)
    # One merged into the one that then went: followed on.
    await _merged(adb, earlier, gone)
    for old in (gone, earlier):
        response = await client.get(f"/sources/{old}")
        assert response.status_code == 301, old
        assert response.headers["location"] == f"/sources/{kept}"
    # An undone merge put its source back; if that's gone since, it's a 404.
    undone = uuid.uuid4()
    await _merged(adb, undone, kept, undone=True)
    assert (await client.get(f"/sources/{undone}")).status_code == 404
    # Never to a source that isn't everyone's: that would say it's there.
    ann = await people("ann")
    box = (
        await ann.post("/api/sources/family", json={"title": "Secret Box", "acknowledged": True})
    ).json()["id"]
    into_private = uuid.uuid4()
    await _merged(adb, into_private, box)
    assert (await client.get(f"/sources/{into_private}")).status_code == 404


async def test_only_a_records_own_page_is_filled(admin, adb, client) -> None:
    """/recipes/<id>/edit and the like are the SPA's alone, as before; here,
    with no built SPA to fall through to, that's a plain 404."""
    book = await _book(admin)
    recipe = await _recipe(admin, adb, book)
    for path in (f"/recipes/{recipe}/edit", f"/sources/{book}/edit", "/recipes/not-an-id"):
        response = await client.get(path)
        assert response.status_code == 404 and "Banana Bread" not in response.text, path


# Pages with no record


@pytest.mark.parametrize(
    "path, robots",
    [
        ("search", "noindex, follow"),
        ("saved", "noindex"),
        ("shelf", "noindex"),
        ("larder", "noindex"),
        ("groups", "noindex"),
        ("groups/123", "noindex"),
        ("account", "noindex"),
        ("admin", "noindex"),
        ("admin/people", "noindex"),
        ("requests", "noindex"),
        ("", None),
        ("sources", None),
        ("ingredients", None),
        ("authors/123", None),
        # Not the admin pages, whatever it starts with.
        ("administer", None),
    ],
)
def test_personal_and_admin_pages_arent_indexed(tmp_path, path, robots) -> None:
    assert pages.robots_for(path) == robots
    (tmp_path / "index.html").write_text("<html><head><title>x</title></head><body></body></html>")
    response = spa_response(tmp_path, path, None, "", pages.robots_for(path))
    if robots is None:
        assert response.path == tmp_path / "index.html"
    else:
        assert f'<meta name="robots" content="{robots}" />' in response.body.decode()
        assert response.headers["cache-control"] == "no-cache"


def test_a_tag_index_html_lacks_is_added_once() -> None:
    page = pages.Page(title="T", description="D", path="/recipes/1")
    filled = pages.fill("<html><head></head><body></body></html>", page, "https://x.example/")
    assert filled == (
        "<html><head><title>T</title>"
        '<meta property="og:title" content="T" />'
        '<meta name="description" content="D" />'
        '<meta property="og:description" content="D" />'
        '<link rel="canonical" href="https://x.example/recipes/1" />'
        '<meta property="og:url" content="https://x.example/recipes/1" />'
        '<meta property="og:type" content="website" />'
        "</head><body></body></html>"
    )
