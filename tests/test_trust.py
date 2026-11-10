"""Trusted contributors (trust.py): earned, granted, withheld."""

import pytest
from sqlalchemy import text

from fake_broker import _settings


@pytest.fixture
def low_bar(configure):
    """Three approved recipes in two books make a contributor trusted."""
    configure(_settings(trust_recipes=3, trust_books=2))


async def _books(mo, adb, *titles):
    out = []
    for title in titles:
        book = (await mo.post("/api/sources/manual", json={"title": title, "authors": []})).json()[
            "id"
        ]
        edition = str(
            await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
        )
        out.append((book, edition))
    return out


async def _add(c, book, edition, title):
    r = await c.post(
        f"/api/sources/{book}/recipes",
        json={"title": title, "editions": [{"edition_id": edition}], "ingredients": []},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _review(adb, recipe):
    return await adb.scalar(text("SELECT review FROM recipes WHERE id = :r"), {"r": recipe})


async def test_trust_is_earned_by_recipes_across_books(low_bar, people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    (a, ea), (b, eb) = await _books(mo, adb, "Plenty", "Jerusalem")
    one, two = await _add(con, a, ea, "One"), await _add(con, a, ea, "Two")
    three = await _add(con, a, ea, "Three")
    for r in (one, two, three):
        assert (
            await mo.post(f"/api/review/recipes/{r}", json={"action": "approve"})
        ).status_code == 200
    # Three recipes, but one book: not yet.
    progress = (await con.get("/api/account/trust")).json()
    assert (progress["recipes"], progress["books"], progress["trusted"]) == (3, 1, False)
    four = await _add(con, b, eb, "Four")
    assert await _review(adb, four) == "pending"
    await mo.post(f"/api/review/recipes/{four}", json={"action": "approve"})
    assert (await con.get("/api/account/trust")).json() == {
        "trusted": True,
        "trust": "earned",
        "recipes": 4,
        "books": 2,
        "needs_recipes": 3,
        "needs_books": 2,
    }
    assert (await con.get("/api/auth/me")).json()["trusted"]
    # Now what they add is published at once, books too.
    five = await _add(con, b, eb, "Five")
    assert await _review(adb, five) == "published"
    book = (await con.post("/api/sources/manual", json={"title": "Simple", "authors": []})).json()[
        "id"
    ]
    assert (
        await adb.scalar(text("SELECT review FROM sources WHERE id = :s"), {"s": book})
        == "published"
    )


async def test_approving_a_whole_book_counts(low_bar, people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    (a, ea), (b, eb) = await _books(mo, adb, "Plenty", "Jerusalem")
    for title in ("One", "Two"):
        await _add(con, a, ea, title)
    await _add(con, b, eb, "Three")
    await mo.post(f"/api/review/sources/{a}/approve-all")
    assert not (await con.get("/api/auth/me")).json()["trusted"]
    await mo.post(f"/api/review/sources/{b}/approve-all")
    assert (await con.get("/api/auth/me")).json()["trusted"]


async def test_withheld_sticks_and_granted_needs_nothing(low_bar, people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    cy = await people("cy", role="contributor")
    con_id = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'con'"))
    cy_id = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'cy'"))
    r = await mo.put(f"/api/admin/people/{con_id}/trust", json={"trust": "withheld"})
    assert r.status_code == 200 and r.json()["trust"] == "withheld"
    (a, ea), (b, eb) = await _books(mo, adb, "Plenty", "Jerusalem")
    for book, edition, title in ((a, ea, "One"), (a, ea, "Two"), (b, eb, "Three")):
        rid = await _add(con, book, edition, title)
        await mo.post(f"/api/review/recipes/{rid}", json={"action": "approve"})
    assert not (await con.get("/api/auth/me")).json()["trusted"]
    # Cleared: the next approval earns it.
    await mo.put(f"/api/admin/people/{con_id}/trust", json={"trust": None})
    rid = await _add(con, b, eb, "Four")
    await mo.post(f"/api/review/recipes/{rid}", json={"action": "approve"})
    assert (await con.get("/api/account/trust")).json()["trust"] == "earned"
    # Granted by hand, with nothing approved.
    await mo.put(f"/api/admin/people/{cy_id}/trust", json={"trust": "granted"})
    assert await _review(adb, await _add(cy, a, ea, "Cy's")) == "published"


async def test_who_sets_trust_and_on_whom(people, adb) -> None:
    mo, con = await people("mo", role="moderator"), await people("con", role="contributor")
    ad = await people("ad", admin=True)
    ad_id = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'ad'"))
    con_id = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'con'"))
    mo_id = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'mo'"))
    assert (
        await con.put(f"/api/admin/people/{con_id}/trust", json={"trust": "granted"})
    ).status_code == 403
    assert (
        await mo.put(f"/api/admin/people/{ad_id}/trust", json={"trust": "granted"})
    ).status_code == 409
    assert (
        await mo.put(f"/api/admin/people/{mo_id}/trust", json={"trust": "granted"})
    ).status_code == 403
    listed = {p["name"]: p["trust"] for p in (await ad.get("/api/admin/people")).json()}
    assert listed["con"] is None


def test_the_bar_is_a_setting() -> None:
    settings = _settings()
    assert (settings.trust_recipes, settings.trust_books) == (250, 5)
