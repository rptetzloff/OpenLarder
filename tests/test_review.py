"""Review (migration 0041, routers/review.py): a contributor's books and
recipes wait, hidden, for a moderator; the agreement comes first."""

import pytest
from sqlalchemy import text

from openlarder import agreement
from test_privacy import _sweep

SECRETS = ("Hidden Larder", "Quietly Pending Pie", "Moonberry Dust", "Penny Pendingham")


async def _book(c, title="Hidden Larder", authors=("Penny Pendingham",)):
    r = await c.post("/api/sources/manual", json={"title": title, "authors": list(authors)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def _edition(adb, book):
    return str(await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book}))


async def _recipe(c, adb, book, title="Quietly Pending Pie", lines=("Moonberry Dust", "Butter")):
    r = await c.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": title,
            "editions": [{"edition_id": await _edition(adb, book)}],
            "ingredients": list(lines),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _review(adb, table, id_):
    return await adb.scalar(text(f"SELECT review FROM {table} WHERE id = :i"), {"i": id_})


# The agreement


async def test_adding_needs_the_agreement_first(people) -> None:
    con = await people("con", role="contributor", agreed=False)
    assert not (await con.get("/api/auth/me")).json()["agreed"]
    refused = await con.post("/api/sources/manual", json={"title": "Plenty"})
    assert refused.status_code == 403 and "agreement" in refused.json()["detail"]
    terms = (await con.get("/api/agreement")).json()
    assert terms["version"] == agreement.VERSION and any("ODbL" in p for p in terms["points"])
    stale = await con.post("/api/account/agreement", json={"version": "1999-01-01"})
    assert stale.status_code == 409
    assert (await con.post("/api/account/agreement", json=terms)).status_code == 204
    assert (await con.get("/api/auth/me")).json()["agreed"]
    assert (await con.post("/api/sources/manual", json={"title": "Plenty"})).status_code == 200


async def test_moderators_and_admins_need_it_too(people) -> None:
    ad = await people("ad", admin=True, agreed=False)
    assert (await ad.post("/api/sources/manual", json={"title": "X"})).status_code == 403
    assert (
        await ad.post("/api/import/runs", json={"books_in_list": 0, "recipes_in_file": 0})
    ).status_code == 403
    assert (await ad.get("/api/import/runs")).status_code == 200


async def test_a_family_collection_needs_no_agreement(people) -> None:
    ann = await people("ann", agreed=False)
    box = await ann.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
    recipe = await ann.post(
        f"/api/sources/{box.json()['id']}/recipes",
        json={"title": "Fudge", "ingredients": ["sugar"]},
    )
    assert recipe.status_code == 201
    shown = (await ann.get(f"/api/recipes/{recipe.json()['id']}")).json()
    assert shown["review"] == "published"


# Waiting


async def test_a_contributors_book_and_recipe_wait_hidden(people, client, adb) -> None:
    con, other = await people("con", role="contributor"), await people("cy", role="contributor")
    mo, plain = await people("mo", role="moderator"), await people("plain")
    book = await _book(con)
    recipe = await _recipe(con, adb, book)
    assert await _review(adb, "sources", book) == "pending"
    assert await _review(adb, "recipes", recipe) == "pending"
    for c in (client, plain, other):
        assert (await c.get(f"/api/sources/{book}")).status_code == 404
        assert (await c.get(f"/api/recipes/{recipe}")).status_code == 404
        assert "Hidden Larder" not in (await c.get("/api/sources", params={"q": "Hidden"})).text
    mine = (await con.get(f"/api/sources/{book}")).json()
    assert mine["review"] == "pending" and mine["details_editable"]
    assert [r["review"] for r in mine["recipes"]] == ["pending"]
    assert (await mo.get(f"/api/recipes/{recipe}")).json()["review"] == "pending"


async def test_a_recipe_in_a_published_book_waits_alone(people, client, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    book = await _book(mo, "Plenty", ("Yotam Ottolenghi",))
    shown = await _recipe(mo, adb, book, "Shakshuka", ("eggs",))
    waiting = await _recipe(con, adb, book)
    page = (await client.get(f"/api/sources/{book}")).json()
    assert [r["title"] for r in page["recipes"]] == ["Shakshuka"]
    assert "Moonberry" not in str(page)
    assert (await client.get(f"/api/recipes/{waiting}")).status_code == 404
    assert (await client.get(f"/api/recipes/{shown}")).status_code == 200
    lines = (await client.get(f"/api/sources/{book}/recipe-lines")).json()
    assert [r["id"] for r in lines] == [shown]
    history = (await client.get(f"/api/sources/{book}/history")).text
    assert "Quietly Pending Pie" not in history and "Moonberry" not in history
    assert "Shakshuka" in history


async def test_a_contributor_changes_only_their_own_waiting_recipes(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    cy = await people("cy", role="contributor")
    book = await _book(mo, "Plenty", ())
    published = await _recipe(mo, adb, book, "Shakshuka", ("eggs",))
    mine = await _recipe(con, adb, book)
    body = {
        "title": "Changed",
        "editions": [{"edition_id": await _edition(adb, book)}],
        "ingredients": [],
    }
    assert (await con.put(f"/api/recipes/{published}", json=body)).status_code == 403
    assert (await con.delete(f"/api/recipes/{published}")).status_code == 403
    assert (await cy.put(f"/api/recipes/{mine}", json=body)).status_code == 404
    assert (await con.put(f"/api/recipes/{mine}", json=body)).status_code == 200
    assert (await con.delete(f"/api/recipes/{mine}")).status_code == 204


async def test_contributors_add_books_only(people) -> None:
    con = await people("con", role="contributor")
    site = await con.post(
        "/api/sources/websites", json={"url": "https://example.com", "title": "Ex"}
    )
    assert site.status_code == 403
    assert (
        await (await people("plain")).post("/api/sources/manual", json={"title": "X"})
    ).status_code == 403


async def test_someone_elses_waiting_book_isnt_pointed_to(people, adb, openlib) -> None:
    con, cy = await people("con", role="contributor"), await people("cy", role="contributor")
    first = await con.post("/api/sources", json={"isbn": "9780393541113"})
    assert first.status_code == 201
    again = await cy.post("/api/sources", json={"isbn": "9780393541113"})
    assert again.status_code == 409 and "source_id" not in again.json()["detail"]
    assert "waiting for review" in again.json()["detail"]["message"]
    by_hand = await cy.post("/api/sources/manual", json={"title": "Love Is a Pink Cake"})
    if by_hand.status_code == 409:
        assert "source_id" not in by_hand.json()["detail"]


# Reviewing


async def test_sent_back_fixed_and_approved(people, client, adb) -> None:
    con, mo = await people("con", role="contributor"), await people("mo", role="moderator")
    book = await _book(con)
    recipe = await _recipe(con, adb, book)
    assert (await con.get("/api/review")).status_code == 403
    [group] = (await mo.get("/api/review")).json()["groups"]
    assert group["source"]["title"] == "Hidden Larder" and group["source"]["by"] == "con"
    assert [r["title"] for r in group["recipes"]] == ["Quietly Pending Pie"]
    assert (
        await mo.post(f"/api/review/recipes/{recipe}", json={"action": "return", "note": " "})
    ).status_code == 422
    back = await mo.post(
        f"/api/review/recipes/{recipe}", json={"action": "return", "note": "Page number, please."}
    )
    assert back.json()["review"] == "returned"
    [mine] = (await con.get("/api/account/contributions")).json()
    assert mine["recipes"][0]["review_note"] == "Page number, please."
    assert (await con.get(f"/api/recipes/{recipe}")).json()["review_note"] == "Page number, please."
    body = {
        "title": "Quietly Pending Pie",
        "editions": [{"edition_id": await _edition(adb, book), "page": "12"}],
        "ingredients": ["Moonberry Dust"],
    }
    assert (await con.put(f"/api/recipes/{recipe}", json=body)).status_code == 200
    assert await _review(adb, "recipes", recipe) == "pending"
    assert (
        await mo.post(f"/api/review/sources/{book}", json={"action": "approve"})
    ).status_code == 200
    assert (
        await mo.post(f"/api/review/recipes/{recipe}", json={"action": "approve"})
    ).status_code == 200
    assert (await client.get(f"/api/recipes/{recipe}")).status_code == 200
    assert (await con.get("/api/account/contributions")).json() == []
    again = await mo.post(f"/api/review/recipes/{recipe}", json={"action": "approve"})
    assert again.status_code == 409


async def test_approve_all_leaves_whats_sent_back(people, adb) -> None:
    con, mo = await people("con", role="contributor"), await people("mo", role="moderator")
    book = await _book(con)
    one = await _recipe(con, adb, book, "One", ("a",))
    two = await _recipe(con, adb, book, "Two", ("b",))
    await mo.post(f"/api/review/recipes/{two}", json={"action": "return", "note": "Fix it."})
    done = (await mo.post(f"/api/review/sources/{book}/approve-all")).json()
    assert done == {"source": True, "recipes": 1}
    assert await _review(adb, "sources", book) == "published"
    assert (await _review(adb, "recipes", one), await _review(adb, "recipes", two)) == (
        "published",
        "returned",
    )


async def test_approving_a_book_links_its_request_and_leaves_it_open(
    people, client, openlib, adb
) -> None:
    """Ray, 2026-11-10: a request is open "until marked finished"."""
    await client.post("/api/requests", json={"isbn": "9780393541113"})
    con, mo = await people("con", role="contributor"), await people("mo", role="moderator")
    book = (await con.post("/api/sources", json={"isbn": "9780393541113"})).json()["id"]
    [waiting] = (await client.get("/api/requests")).json()["requests"]
    assert waiting["source_id"] is None
    await mo.post(f"/api/review/sources/{book}", json={"action": "approve"})
    [linked] = (await client.get("/api/requests")).json()["requests"]
    assert (linked["status"], linked["source_id"]) == ("open", book)


async def test_a_waiting_recipe_shows_its_new_ingredients(people, adb) -> None:
    """The matching flow's last step: what a recipe brings into the catalog,
    for a moderator to keep or merge into what it's another name for."""
    mo = await people("mo", role="moderator")
    published = await _book(mo, "Pantry")
    await _recipe(mo, adb, published, "Toast", ("Butter",))
    con = await people("con", role="contributor")
    book = await _book(con)
    pie = await _recipe(con, adb, book, "Pie", ("Moonberry Dust", "Butter", "Moonberry Dust"))
    tart = await _recipe(con, adb, book, "Tart", ("Moonberry dust",))
    [group] = [
        g for g in (await mo.get("/api/review")).json()["groups"] if g["source"]["id"] == book
    ]
    new = {r["title"]: [i["name"] for i in r["new_ingredients"]] for r in group["recipes"]}
    # Butter is in a published recipe; Moonberry Dust only in waiting ones.
    assert new == {"Pie": ["Moonberry Dust"], "Tart": ["Moonberry Dust"]}
    # Merged into one that's here: it's that one's other name, and no longer new.
    dust = group["recipes"][0]["new_ingredients"][0]["id"]
    butter = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Butter'"))
    r = await mo.post(f"/api/ingredients/{dust}/merge", json={"into": str(butter)})
    assert r.status_code == 200, r.text
    [group] = [
        g for g in (await mo.get("/api/review")).json()["groups"] if g["source"]["id"] == book
    ]
    assert [r["new_ingredients"] for r in group["recipes"]] == [[], []]
    assert (
        await adb.scalar(
            text("SELECT count(*) FROM ingredient_aliases WHERE name = 'Moonberry Dust'")
        )
        == 1
    )
    assert pie and tart


# Nothing waiting leaks


@pytest.fixture
async def waiting(people, adb):
    """A contributor's book, its recipe, and the ingredient and author only
    they use, all waiting; in the shape the privacy sweep asks with."""
    con = await people("penny", role="contributor")
    book = await _book(con)
    recipe = await _recipe(con, adb, book)
    dust = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Moonberry Dust'"))
    author = await adb.scalar(text("SELECT id FROM authors WHERE name = 'Penny Pendingham'"))
    butter = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Butter'"))
    group = (await con.post("/api/groups", json={"name": "Nothing here"})).json()["id"]
    return {
        "ann": con,
        "box": book,
        "stew": recipe,
        "salt": dust,
        "author": author,
        "group": group,
        "above": butter,
        "below": butter,
    }


@pytest.mark.parametrize("who", ["nobody", "plain", "contributor"])
async def test_no_get_route_shows_anything_waiting(waiting, people, client, who) -> None:
    other = {
        "nobody": lambda: client,
        "plain": lambda: people("plain"),
        "contributor": lambda: people("cy", role="contributor"),
    }[who]()
    other = other if who == "nobody" else await other
    everything = await _sweep(other, waiting)
    leaked = [s for s in SECRETS if s in everything]
    assert not leaked, leaked
    # The sweep does reach them: their maker's answers have every one.
    mine = await _sweep(waiting["ann"], waiting)
    assert [s for s in SECRETS if s in mine] == list(SECRETS)


async def test_the_views_n8n_reads_leave_out_whats_waiting(waiting, adb) -> None:
    for view, column in (
        ("public_recipes", "title"),
        ("public_ingredient_lines", "original_text"),
        ("public_ingredients", "name"),
    ):
        found = await adb.scalar(text(f"SELECT string_agg({column}, ' ') FROM {view}"))
        assert "Pending" not in (found or "") and "Moonberry" not in (found or ""), view


async def test_a_contributor_tags_only_whats_theirs_and_waiting(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    tag = (await mo.post("/api/tags", json={"kind": "course", "name": "Puddings"})).json()["id"]
    book = await _book(mo, "Plenty", ())
    published = await _recipe(mo, adb, book, "Shakshuka", ("eggs",))
    mine = await _recipe(con, adb, book)
    tags = {"tags": [tag]}
    assert (await con.put(f"/api/sources/{book}/tags", json=tags)).status_code == 403
    assert (await con.put(f"/api/recipes/{published}/tags", json=tags)).status_code == 403
    assert (await con.put(f"/api/recipes/{mine}/tags", json=tags)).status_code == 200
    own = await _book(con)
    assert (await con.put(f"/api/sources/{own}/tags", json=tags)).status_code == 200
    assert not (await con.get(f"/api/sources/{book}")).json()["tags_editable"]
    assert (await con.get(f"/api/sources/{own}")).json()["tags_editable"]


def test_the_accessibility_seed_accepts_the_current_agreement() -> None:
    """web/a11y/users.sql plants people who have accepted it, by version."""
    from pathlib import Path

    seed = (Path(__file__).resolve().parents[1] / "web" / "a11y" / "users.sql").read_text()
    assert f"'{agreement.VERSION}'" in seed
