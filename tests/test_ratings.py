"""Ratings (routers/ratings.py): one to five spoons, shown as an average."""

from sqlalchemy import text


async def _recipe(mo, adb, title="Barley Soup"):
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty"})).json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    r = await mo.post(
        f"/api/sources/{book}/recipes",
        json={"title": title, "editions": [{"edition_id": edition, "page": "12"}]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_spoons_are_averaged_and_never_say_who(people, client, adb) -> None:
    mo, ann, bo = await people("mo", role="moderator"), await people("ann"), await people("bo")
    soup = await _recipe(mo, adb)
    url = f"/api/recipes/{soup}/rating"

    assert (await client.get(url)).json() == {"spoons": None, "ratings": 0, "mine": None}
    assert (await ann.put(url, json={"spoons": 5})).json() == {
        "spoons": 5.0,
        "ratings": 1,
        "mine": 5,
    }
    assert (await bo.put(url, json={"spoons": 2})).json() == {
        "spoons": 3.5,
        "ratings": 2,
        "mine": 2,
    }
    # Changing yours is still one rating.
    assert (await bo.put(url, json={"spoons": 4})).json()["spoons"] == 4.5
    # Signed out: the average, and nothing of whose.
    assert (await client.get(url)).json() == {"spoons": 4.5, "ratings": 2, "mine": None}
    assert (await mo.get(url)).json()["mine"] is None

    for bad in (0, 6, 2.5):
        assert (await ann.put(url, json={"spoons": bad})).status_code == 422
    assert (await client.put(url, json={"spoons": 3})).status_code == 401

    # A listing carries it.
    [hit] = (await client.get("/api/search", params={"q": "barley"})).json()["recipes"]
    assert (hit["spoons"], hit["ratings"]) == (4.5, 2)

    assert (await bo.delete(url)).status_code == 204
    assert (await client.get(url)).json() == {"spoons": 5.0, "ratings": 1, "mine": None}


async def test_a_private_recipe_is_rated_only_by_who_sees_it(people, client) -> None:
    ann, bo = await people("ann"), await people("bo")
    box = (
        await ann.post("/api/sources/family", json={"title": "Gran's Box", "acknowledged": True})
    ).json()["id"]
    fudge = (
        await ann.post(f"/api/sources/{box}/recipes", json={"title": "Fudge", "ingredients": []})
    ).json()["id"]
    url = f"/api/recipes/{fudge}/rating"
    assert (await ann.put(url, json={"spoons": 5})).status_code == 200
    assert (await bo.get(url)).status_code == 404
    assert (await bo.put(url, json={"spoons": 1})).status_code == 404
    assert (await client.get(url)).status_code == 404


async def test_deleting_the_account_takes_its_ratings(people, client, adb) -> None:
    mo, ann = await people("mo", role="moderator"), await people("ann")
    soup = await _recipe(mo, adb)
    await ann.put(f"/api/recipes/{soup}/rating", json={"spoons": 1})
    assert (await ann.post("/api/account/delete", json={"confirm": "ann"})).status_code == 204
    assert (await client.get(f"/api/recipes/{soup}/rating")).json()["ratings"] == 0
