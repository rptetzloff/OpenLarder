"""Private family collections: seen and changed only by their owner.

The sweep at the bottom asks every GET route in the app, as someone else,
for the private things by id and by name, and fails on any trace of them.
A new route with a path parameter it doesn't know fails it too, so each one
gets asked.
"""

import json
import uuid

import httpx2
import pytest
from sqlalchemy import select, text

from openlarder import visibility
from openlarder.main import app
from openlarder.models import Ingredient, Source, User

SECRETS = ("Secret Box", "Secret Stew", "Zanzibar Moonsalt", "Nana Secretta", "Secret Family")


async def _collection(c, title="Secret Box", **more):
    response = await c.post(
        "/api/sources/family", json={"title": title, "acknowledged": True, **more}
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _recipe(c, source, title="Secret Stew", lines=("Zanzibar Moonsalt", "Butter")):
    response = await c.post(
        f"/api/sources/{source}/recipes", json={"title": title, "ingredients": list(lines)}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
async def secret(people, adb):
    """Ann's private collection, its recipe, and the ingredient only it uses."""
    ann = await people("ann")
    box = await _collection(ann)
    stew = await _recipe(ann, box)
    salt = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Zanzibar Moonsalt'"))
    butter = await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Butter'"))
    await adb.execute(
        text("INSERT INTO recipe_flags (recipe_id, kind, detail) VALUES (:r, 'no_page', 'x')"),
        {"r": uuid.UUID(stew)},
    )
    # No route credits anyone on a family collection yet; the database can.
    nana = await adb.scalar(
        text(
            "INSERT INTO authors (name, name_key) VALUES ('Nana Secretta', 'nana secretta')"
            " RETURNING id"
        )
    )
    await adb.execute(
        text(
            "INSERT INTO source_credits (source_id, author_id, position, credited_as)"
            " VALUES (:s, :a, 1, 'Nana Secretta')"
        ),
        {"s": uuid.UUID(box), "a": nana},
    )
    # Pat is credited on a public book and on the box: her page shows only
    # the book.
    pat = await adb.scalar(
        text(
            "INSERT INTO authors (name, name_key) VALUES ('Pat Public', 'pat public') RETURNING id"
        )
    )
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Open Book') RETURNING id"))
    await adb.execute(
        text(
            "INSERT INTO source_credits (source_id, author_id, position, credited_as)"
            " VALUES (:b, :a, 1, 'Pat Public'), (:s, :a, 2, 'Pat Public')"
        ),
        {"b": book, "s": uuid.UUID(box), "a": pat},
    )
    # The salt sits in the hierarchy between two ingredients nothing uses,
    # so both of their pages would name it.
    above = await adb.scalar(
        text("INSERT INTO ingredients (name, match_key) VALUES ('Salt', 'salt') RETURNING id")
    )
    below = await adb.scalar(
        text(
            "INSERT INTO ingredients (name, match_key, parent_id)"
            " VALUES ('Smoked Flakes', 'smoked flake', :p) RETURNING id"
        ),
        {"p": salt},
    )
    await adb.execute(
        text("UPDATE ingredients SET parent_id = :a WHERE id = :s"), {"a": above, "s": salt}
    )
    # Ann's group, which the box is shared with; nobody else is in it.
    group = (await ann.post("/api/groups", json={"name": "Secret Family"})).json()["id"]
    shared = await ann.put(f"/api/sources/{box}/groups", json={"groups": [group]})
    assert shared.status_code == 200, shared.text
    return {
        "ann": ann,
        "group": group,
        "box": box,
        "stew": stew,
        "salt": salt,
        "butter": butter,
        "author": nana,
        "pat": pat,
        "above": above,
        "below": below,
    }


# Adding one


async def test_anyone_signed_in_adds_a_private_collection(people, client) -> None:
    ann = await people("ann")
    box = await _collection(ann, "  Grandma's  Recipe Box ")
    shown = (await ann.get(f"/api/sources/{box}")).json()
    assert (shown["kind"], shown["title"], shown["private"], shown["editable"]) == (
        "family",
        "Grandma's Recipe Box",
        True,
        True,
    )
    assert (await client.post("/api/sources/family", json={"title": "X"})).status_code == 401


async def test_adding_needs_the_tick(people) -> None:
    ann = await people("ann")
    response = await ann.post("/api/sources/family", json={"title": "Box"})
    assert response.status_code == 422
    assert "Tick" in response.json()["detail"]


async def test_only_an_admin_adds_a_public_one_for_now(people) -> None:
    ann = await people("ann")
    refused = await ann.post(
        "/api/sources/family", json={"title": "Box", "acknowledged": True, "private": False}
    )
    assert refused.status_code == 403
    admin = await people("ada", admin=True)
    public = await _collection(admin, "St. Mary's 1978", private=False)
    assert (await ann.get(f"/api/sources/{public}")).json()["private"] is False


async def test_one_name_is_one_collection_per_owner(people) -> None:
    ann, bob = await people("ann"), await people("bob")
    first = await _collection(ann, "Recipe Box")
    again = await ann.post(
        "/api/sources/family", json={"title": "recipe box", "acknowledged": True}
    )
    assert again.json() == {"id": first, "existing": True}
    assert await _collection(bob, "Recipe Box") != first


async def test_the_tick_is_recorded(people, adb) -> None:
    box = await _collection(await people("ann"))
    assert await adb.scalar(
        text("SELECT acknowledged_at IS NOT NULL FROM sources WHERE id = :s"), {"s": box}
    )


# The owner's


async def test_the_owner_adds_and_changes_recipes(secret) -> None:
    ann = secret["ann"]
    recipe = (await ann.get(f"/api/recipes/{secret['stew']}")).json()
    assert (recipe["title"], recipe["editable"], recipe["pages"]) == ("Secret Stew", True, [])
    changed = await ann.put(
        f"/api/recipes/{secret['stew']}",
        json={"title": "Secret Soup", "ingredients": ["Zanzibar Moonsalt"]},
    )
    assert changed.status_code == 200, changed.text
    assert (await ann.delete(f"/api/recipes/{secret['stew']}")).status_code == 204


async def test_the_owner_deals_with_their_recipes_flags(secret, people) -> None:
    flags = (await secret["ann"].get(f"/api/recipes/{secret['stew']}/flags")).json()
    assert [f["kind"] for f in flags] == ["no_page"]
    mine = (await secret["ann"].get("/api/flags")).json()
    assert mine["total"] == 1


async def test_a_family_recipe_has_no_page(secret, adb) -> None:
    response = await secret["ann"].post(
        f"/api/sources/{secret['box']}/recipes",
        json={"title": "Pie", "web_address": "https://example.com/pie", "ingredients": []},
    )
    assert response.status_code == 422
    assert "in a family collection" in response.json()["detail"]


async def test_the_owner_renames_and_deletes_it(secret, adb) -> None:
    ann, box = secret["ann"], secret["box"]
    renamed = await ann.patch(f"/api/sources/{box}/family", json={"title": "Old Box"})
    assert renamed.status_code == 200
    assert (await ann.get(f"/api/sources/{box}")).json()["title"] == "Old Box"
    public = await ann.patch(f"/api/sources/{box}/family", json={"private": False})
    assert public.status_code == 403
    assert (await ann.delete(f"/api/sources/{box}")).status_code == 204
    assert await adb.scalar(text("SELECT count(*) FROM recipes")) == 0


async def test_only_a_family_collection_is_deleted_this_way(people, adb) -> None:
    admin = await people("ada", admin=True)
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    assert (await admin.delete(f"/api/sources/{book}")).status_code == 409


# Everyone else's


@pytest.mark.parametrize("who", ["nobody", "bob", "moderator", "admin", "owner"])
async def test_nobody_else_sees_or_changes_it(secret, people, client, who) -> None:
    other = {
        "nobody": lambda: client,
        "bob": lambda: people("bob"),
        "moderator": lambda: people("mo", role="moderator"),
        "admin": lambda: people("ada", admin=True),
        "owner": lambda: people("own", role="owner"),
    }[who]()
    other = await other if not isinstance(other, httpx2.AsyncClient) else other
    box, stew = secret["box"], secret["stew"]
    assert (await other.get(f"/api/sources/{box}")).status_code == 404
    assert (await other.get(f"/api/recipes/{stew}")).status_code == 404
    if who == "nobody":
        return
    body = {"title": "Mine now", "ingredients": []}
    assert (await other.post(f"/api/sources/{box}/recipes", json=body)).status_code == 404
    assert (await other.put(f"/api/recipes/{stew}", json=body)).status_code == 404
    assert (await other.delete(f"/api/recipes/{stew}")).status_code == 404
    # The book editor is a moderator's: 403 for Bob, and 404 for a moderator up.
    editing = await other.put(f"/api/sources/{box}", json={"title": "X"})
    assert editing.status_code == (403 if who == "bob" else 404)
    assert (await other.patch(f"/api/sources/{box}/family", json={"title": "X"})).status_code == 404
    assert (await other.delete(f"/api/sources/{box}")).status_code == 404
    assert (await other.get(f"/api/recipes/{stew}/flags")).status_code == 404


async def test_a_shared_ingredient_counts_only_what_you_see(secret, people, adb) -> None:
    admin = await people("ada", admin=True)
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    await adb.execute(text("INSERT INTO editions (source_id) VALUES (:b)"), {"b": book})
    edition = await adb.scalar(text("SELECT id FROM editions WHERE source_id = :b"), {"b": book})
    made = await admin.post(
        f"/api/sources/{book}/recipes",
        json={
            "title": "Shortbread",
            "editions": [{"edition_id": str(edition)}],
            "ingredients": ["Butter"],
        },
    )
    assert made.status_code == 201, made.text
    butter = secret["butter"]
    for who, expected in ((admin, 1), (secret["ann"], 2)):
        page = (await who.get(f"/api/ingredients/{butter}")).json()
        listed = (await who.get("/api/ingredients", params={"q": "Butter"})).json()
        assert (page["total"], listed["ingredients"][0]["recipes"]) == (expected, expected)
    found = (await admin.get("/api/search", params={"ingredient": [str(butter)]})).json()
    assert [r["title"] for r in found["recipes"]] == ["Shortbread"]


async def test_checking_a_line_finds_only_what_you_see(secret, people) -> None:
    """The add-a-recipe form's check is a POST, so the sweep doesn't ask it."""
    lines = ["Zanzibar Moonsalt", "Zanzibar Moonsal"]

    async def read(who, **more):
        return await who.post("/api/ingredient-lines/check", json={"lines": lines, **more})

    def found(response):
        assert response.status_code == 200, response.text
        options = [r["options"][0] for r in response.json()["lines"]]
        return [(o["ingredient"], o["similar"]) for o in options]

    salt = {"id": str(secret["salt"]), "name": "Zanzibar Moonsalt"}
    assert found(await read(await people("bob", admin=True))) == [(None, []), (None, [])]
    assert found(await read(secret["ann"])) == [(salt, []), (None, [salt])]
    # Nor does anyone else learn the box is there.
    assert (await read(await people("cat"), source_id=secret["box"])).status_code == 404


async def test_the_list_hides_a_parent_you_cant_see(secret, people) -> None:
    """Smoked Flakes sits under the private salt: to anyone else it comes
    under nothing, so it is top level."""
    bob = await people("bob")
    listed = (await bob.get("/api/ingredients", params={"q": "smoked"})).json()["ingredients"]
    assert [(i["name"], i["parent"]) for i in listed] == [("Smoked Flakes", None)]
    top = (await bob.get("/api/ingredients", params={"top": "true", "q": "smoked"})).json()
    assert [i["name"] for i in top["ingredients"]] == ["Smoked Flakes"]
    mine = (await secret["ann"].get("/api/ingredients", params={"q": "smoked"})).json()
    assert mine["ingredients"][0]["parent"]["name"] == "Zanzibar Moonsalt"


async def test_the_author_list_counts_only_what_you_see(secret, people) -> None:
    """Pat is credited on a public book and on the private box: to anyone
    else, Pat is known for the book and has none of the box's recipes."""
    bob = await people("bob")
    listed = (await bob.get("/api/authors", params={"q": "pat public"})).json()["authors"]
    assert [(a["sources"], a["recipes"], a["known_for"]["title"]) for a in listed] == [
        (1, 0, "Open Book")
    ]
    mine = (await secret["ann"].get("/api/authors", params={"q": "pat public"})).json()
    assert [(a["sources"], a["recipes"]) for a in mine["authors"]] == [(2, 1)]


async def test_the_views_for_n8n_leave_out_the_private_collection(secret, adb) -> None:
    """What local models read (migration 0029): what someone signed out sees."""
    public = set(await adb.scalars(text("SELECT id FROM public_ingredients")))
    seen = set(await adb.scalars(select(Ingredient.id).where(visibility.ingredients_seen_by(None))))
    assert public == seen
    # Nothing uses Salt; only the private stew uses the moonsalt and butter.
    assert secret["above"] in public and secret["salt"] not in public
    # Smoked Flakes sits under the private salt: it reads as top level.
    assert (
        await adb.scalar(
            text("SELECT parent_id FROM public_ingredients WHERE id = :i"), {"i": secret["below"]}
        )
        is None
    )
    lines = list(await adb.scalars(text("SELECT original_text FROM public_ingredient_lines")))
    assert "Zanzibar Moonsalt" not in lines
    flags = list(await adb.scalars(text("SELECT recipe_id FROM public_open_flags")))
    assert uuid.UUID(secret["stew"]) not in flags
    # Workflow 4's views (0033), with the stew and its box tagged.
    vegan = await adb.scalar(text("SELECT id FROM tags WHERE name = 'Vegan'"))
    await adb.execute(
        text("INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (:r, :t)"),
        {"r": uuid.UUID(secret["stew"]), "t": vegan},
    )
    await adb.execute(
        text("INSERT INTO source_tags (source_id, tag_id) VALUES (:s, :t)"),
        {"s": uuid.UUID(secret["box"]), "t": vegan},
    )
    recipes = list(await adb.scalars(text("SELECT id FROM public_recipes")))
    tagged = list(await adb.scalars(text("SELECT recipe_id FROM public_recipe_tags")))
    assert uuid.UUID(secret["stew"]) not in recipes + tagged


async def test_counts_leave_out_what_you_cant_see(secret, people, adb) -> None:
    """Counts carry no names, so the sweep can't see them: the flags an
    admin is told of, and the recipes under an ingredient."""
    admin = await people("ada", admin=True)
    # A child of Salt everyone sees, so its family is counted, not assumed.
    await adb.execute(
        text(
            "INSERT INTO ingredients (name, match_key, parent_id)"
            " VALUES ('Sea Salt', 'sea salt', :p)"
        ),
        {"p": secret["above"]},
    )
    flags = (await admin.get("/api/flags", params={"scope": "all"})).json()
    assert (flags["open_by_kind"], flags["total"]) == ({}, 0)
    for who, expected in ((admin, 0), (secret["ann"], 1)):
        above = (await who.get(f"/api/ingredients/{secret['above']}")).json()
        assert above["family_total"] == expected


async def test_a_public_collection_is_still_only_its_owners_to_change(people, adb) -> None:
    ada, bob = await people("ada", admin=True), await people("bob")
    public = await _collection(ada, "St. Mary's 1978", private=False)
    body = {"title": "Pie", "ingredients": []}
    assert (await bob.post(f"/api/sources/{public}/recipes", json=body)).status_code == 403
    assert (await bob.get(f"/api/sources/{public}")).json()["editable"] is False
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    assert (await bob.post(f"/api/sources/{book}/recipes", json=body)).status_code == 403


@pytest.mark.parametrize("role", ["moderator", "admin", "owner"])
def test_no_role_may_change_a_private_collection(role) -> None:
    """Can't happen through the routes, which hide it from them first; the
    rule says so anyway, for every role up to the owner."""
    ann, ada = User(id=uuid.uuid4(), role="user"), User(id=uuid.uuid4(), role=role)
    box = Source(kind="family", owner_id=ann.id, private=True)
    assert (visibility.may_manage(ann, box), visibility.may_manage(ada, box)) == (True, False)
    box.private = False
    assert visibility.may_manage(ada, box)
    # Only a family collection is managed this way; a book is edited by moderators.
    assert not visibility.may_manage(ada, Source(kind="book"))


async def test_a_private_sub_recipe_hides_nothing_else(secret, people, client) -> None:
    """An option naming a sub-recipe has no ingredient; a NULL in the hidden
    list must not hide every ingredient from everyone."""
    ann = secret["ann"]
    await _recipe(ann, secret["box"], "Pastry", ["Flour"])
    await _recipe(ann, secret["box"], "Pie", ["Pastry (p. 1)", "Apples"])
    admin = await people("ada", admin=True)
    book = (await admin.post("/api/sources/manual", json={"title": "Open Book 2"})).json()["id"]
    edition = (await admin.get(f"/api/sources/{book}")).json()["editions"][0]["id"]
    await admin.post(
        f"/api/sources/{book}/recipes",
        json={"title": "Toast", "editions": [{"edition_id": edition}], "ingredients": ["Bread"]},
    )
    listed = (await client.get("/api/ingredients", params={"q": "Bread"})).json()
    assert [i["name"] for i in listed["ingredients"]] == ["Bread"]


async def test_the_owner_finds_their_own(secret) -> None:
    ann = secret["ann"]
    found = (await ann.get("/api/search", params={"q": "secret"})).json()
    assert [r["title"] for r in found["recipes"]] == ["Secret Stew"]
    listed = (await ann.get("/api/sources", params={"q": "secret"})).json()
    assert [(s["title"], s["private"]) for s in listed["sources"]] == [("Secret Box", True)]
    salt = (await ann.get(f"/api/ingredients/{secret['salt']}")).json()
    assert [r["title"] for r in salt["recipes"]] == ["Secret Stew"]


# The sweep


def _get_routes() -> list[tuple[str, list[str]]]:
    """Every GET route under /api, with its path parameters' names. Read
    from the OpenAPI schema, since app.routes nests included routers."""
    return [
        (path, [x["name"] for x in ops["get"].get("parameters", []) if x["in"] == "path"])
        for path, ops in app.openapi()["paths"].items()
        if "get" in ops and path.startswith("/api")
    ]


def _fill(path: str, names: list[str], secret: dict) -> str:
    """The route's path asking for the private things."""
    values = {
        "source_id": secret["box"],
        "recipe_id": secret["stew"],
        "ingredient_id": secret["salt"],
        "author_id": secret["author"],
        "group_id": secret["group"],
        # An invite's token is itself the secret: whoever has it may see the
        # group's name. The sweep asks without one.
        "code": "not-a-real-invite",
        "run_id": uuid.uuid4(),
    }
    for name in names:
        assert name in values, f"{path}: tell the privacy sweep what {name} to ask for"
        path = path.replace("{" + name + "}", str(values[name]))
    return path


QUERIES = {
    "/api/search": {"q": "Secret", "ingredient": None, "source": None},
    "/api/sources": {"q": "Secret"},
    "/api/ingredients": {"q": "Moonsalt"},
    "/api/authors": {"q": ""},
    "/api/flags": {"scope": "all"},
}


async def _sweep(c: httpx2.AsyncClient, secret: dict) -> str:
    """Every GET route's answers, joined, as this client sees them."""
    seen = []
    routes = _get_routes()
    assert len(routes) >= 15, routes
    for route, names in routes:
        path = _fill(route, names, secret)
        params = dict(QUERIES.get(route, {}))
        if route == "/api/search":
            params.update(ingredient=[str(secret["salt"])], source=[secret["box"]])
        response = await c.get(path, params=params)
        assert response.status_code < 500, (route, response.text)
        seen.append(response.text)
        if route == "/api/ingredients":
            # And unfiltered, where a hidden ingredient would otherwise show.
            seen.append((await c.get(path)).text)
        if route == "/api/authors/{author_id}":
            for other in ("twin", "pat"):
                if other in secret:
                    seen.append((await c.get(f"/api/authors/{secret[other]}")).text)
        if route == "/api/ingredients/{ingredient_id}":
            for other in ("above", "below"):
                seen.append((await c.get(f"/api/ingredients/{secret[other]}")).text)
    return "\n".join(seen)


@pytest.mark.parametrize("who", ["nobody", "bob", "admin"])
async def test_no_get_route_shows_anything_private(secret, people, client, adb, who) -> None:
    # Another record of her name, whose page would list her as the same name.
    twin = await adb.scalar(
        text(
            "INSERT INTO authors (name, name_key) VALUES ('Nana  Secretta', 'nana secretta')"
            " RETURNING id"
        )
    )
    secret["twin"] = twin
    other = client if who == "nobody" else await people(who, admin=who == "admin")
    everything = await _sweep(other, secret)
    leaked = [s for s in SECRETS if s in everything]
    assert not leaked, leaked
    # The sweep does reach them: the owner's answers have every one.
    mine = await _sweep(secret["ann"], secret)
    assert [s for s in SECRETS if s in mine] == list(SECRETS)


# What the database refuses


@pytest.mark.parametrize(
    ("columns", "values", "refused_by"),
    [
        ("title, private", "'Book', true", "ck_sources_private_only_family"),
        ("title, kind, acknowledged_at", "'Box', 'family', now()", "ck_sources_owner_for_family"),
        ("title, kind, owner_id", "'Box', 'family', :u", "ck_sources_family_acknowledged"),
        ("title, owner_id", "'Book', :u", "ck_sources_owner_for_family"),
    ],
)
async def test_the_database_refuses_a_bad_collection(people, adb, columns, values, refused_by):
    await people("ann")
    user = await adb.scalar(text("SELECT id FROM users WHERE subject = 'ann'"))
    with pytest.raises(Exception, match=refused_by):
        async with adb.begin_nested():
            await adb.execute(
                text(f"INSERT INTO sources ({columns}) VALUES ({values})"), {"u": user}
            )


async def test_an_owner_with_a_collection_is_kept(secret, adb) -> None:
    with pytest.raises(Exception, match="fk_sources_owner_id_users"):
        async with adb.begin_nested():
            await adb.execute(text("DELETE FROM users WHERE subject = 'ann'"))


async def test_a_suggestion_naming_a_private_ingredient_stays_hidden(secret, people, adb) -> None:
    """n8n read only public data, but a suggestion outlives that: the salt
    is used only by Ann's box now, so an admin is neither shown nor able to
    act on a suggestion naming it."""
    proposal = {
        "a_id": str(secret["above"]),
        "b_id": str(secret["salt"]),
        "decision": "same",
        "keep_name": "a",
        "similarity": "0.9",
    }
    suggestion = await adb.scalar(
        text(
            "INSERT INTO suggestions (kind, target, proposal, model, prompt_version)"
            " VALUES ('merge', CAST(:t AS jsonb), CAST(:p AS jsonb), 'm', 'v') RETURNING id"
        ),
        {
            "t": json.dumps(sorted([str(secret["above"]), str(secret["salt"])])),
            "p": json.dumps(proposal),
        },
    )
    admin = await people("ada", admin=True)
    page = (await admin.get("/api/suggestions")).json()
    assert page["suggestions"] == [] and page["open_by_kind"] == {}
    for action in ("accept", "dismiss"):
        refused = await admin.post(f"/api/suggestions/{suggestion}/{action}", json={})
        assert refused.status_code == 404


async def test_searching_by_tag_leaves_out_the_private_collection(secret, people, adb) -> None:
    """A tag on Ann's box, and on her stew, finds nothing for anyone else."""
    vegan = await adb.scalar(text("SELECT id FROM tags WHERE kind = 'diet' AND name = 'Vegan'"))
    await adb.execute(
        text("INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (:r, :t)"),
        {"r": uuid.UUID(secret["stew"]), "t": vegan},
    )
    await adb.execute(
        text("INSERT INTO source_tags (source_id, tag_id) VALUES (:s, :t)"),
        {"s": uuid.UUID(secret["box"]), "t": vegan},
    )
    for who in (await people("ada", admin=True), await people("bo")):
        found = (await who.get("/api/search", params={"tag": str(vegan)})).json()
        assert found["recipes"] == [] and found["total"] == 0
    mine = (await secret["ann"].get("/api/search", params={"tag": str(vegan)})).json()
    assert [r["id"] for r in mine["recipes"]] == [secret["stew"]]


async def test_a_tag_suggestion_for_a_private_recipe_stays_hidden(secret, people, adb) -> None:
    """The stew is in Ann's box: no admin is shown a tag suggestion for it,
    or can act on one."""
    vegan = await adb.scalar(text("SELECT id FROM tags WHERE name = 'Vegan'"))
    proposal = {"recipe_id": secret["stew"], "tag_id": str(vegan)}
    suggestion = await adb.scalar(
        text(
            "INSERT INTO suggestions (kind, target, proposal, model, prompt_version)"
            " VALUES ('tag', CAST(:t AS jsonb), CAST(:p AS jsonb), 'm', 'v') RETURNING id"
        ),
        {"t": json.dumps([secret["stew"], str(vegan)]), "p": json.dumps(proposal)},
    )
    admin = await people("ada", admin=True)
    page = (await admin.get("/api/suggestions")).json()
    assert page["suggestions"] == [] and page["open_by_kind"] == {}
    for action in ("accept", "dismiss"):
        refused = await admin.post(f"/api/suggestions/{suggestion}/{action}", json={})
        assert refused.status_code == 404
