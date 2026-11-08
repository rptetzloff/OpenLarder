"""Household groups: invites, roles, and sharing private collections."""

import hashlib
import uuid

import pytest
from sqlalchemy import text

from test_privacy import _collection, _recipe


async def _group(c, name="Tetzloff family"):
    response = await c.post("/api/groups", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _invite(c, group, role="view"):
    response = await c.post(f"/api/groups/{group}/invites", json={"role": role})
    assert response.status_code == 201, response.text
    return response.json()


async def _join(c, admin, group, role="view"):
    token = (await _invite(admin, group, role))["token"]
    response = await c.post(f"/api/invites/{token}/accept")
    assert response.status_code == 200, response.text


async def _user_id(adb, name):
    return await adb.scalar(text("SELECT id FROM users WHERE subject = :n"), {"n": name})


@pytest.fixture
async def family(people, adb):
    """Ann's group, with Bob viewing and Cy editing, and Ann's private box
    shared with it."""
    ann, bob, cy = await people("ann"), await people("bob"), await people("cy")
    group = await _group(ann)
    await _join(bob, ann, group, "view")
    await _join(cy, ann, group, "edit")
    box = await _collection(ann, "Grandma's Box")
    stew = await _recipe(ann, box, "Stew", ["Moonsalt"])
    shared = await ann.put(f"/api/sources/{box}/groups", json={"groups": [group]})
    assert shared.status_code == 200, shared.text
    return {"ann": ann, "bob": bob, "cy": cy, "group": group, "box": box, "stew": stew}


# Making one, and invites


async def test_the_maker_is_its_admin(people) -> None:
    ann = await people("ann")
    group = await _group(ann, "  Tetzloff   family ")
    listed = (await ann.get("/api/groups")).json()
    assert listed == [{"id": group, "name": "Tetzloff family", "role": "admin", "members": 1}]
    shown = (await ann.get(f"/api/groups/{group}")).json()
    assert [(m["name"], m["role"]) for m in shown["members"]] == [("ann", "admin")]


async def test_an_invite_brings_one_person_in_once(people, adb) -> None:
    ann, bob, cy = await people("ann"), await people("bob"), await people("cy")
    group = await _group(ann)
    made = await _invite(ann, group, "edit")
    # Only its hash is kept.
    stored = await adb.scalar(text("SELECT token_hash FROM group_invites"))
    assert stored == hashlib.sha256(made["token"].encode()).digest()
    about = await bob.get(f"/api/invites/{made['token']}")
    assert about.json() == {"group": "Tetzloff family", "role": "edit"}
    joined = await bob.post(f"/api/invites/{made['token']}/accept")
    assert (joined.status_code, joined.json()["role"]) == (200, "edit")
    again = await cy.post(f"/api/invites/{made['token']}/accept")
    assert again.status_code == 410
    assert (await cy.get(f"/api/invites/{made['token']}")).status_code == 410
    assert (await cy.get(f"/api/groups/{group}")).status_code == 404


async def test_an_invite_expires(people, adb) -> None:
    ann, bob = await people("ann"), await people("bob")
    group = await _group(ann)
    made = await _invite(ann, group)
    # Seven days, as Ray chose: past six, short of eight.
    assert await adb.scalar(
        text(
            "SELECT expires_at BETWEEN now() + interval '6 days' AND now() + interval '8 days'"
            " FROM group_invites"
        )
    )
    await adb.execute(
        text(
            "UPDATE group_invites SET created_at = now() - interval '8 days',"
            " expires_at = now() - interval '1 day'"
        )
    )
    assert (await bob.post(f"/api/invites/{made['token']}/accept")).status_code == 410
    assert (await bob.get(f"/api/invites/{made['token']}")).status_code == 410
    assert (await ann.get(f"/api/groups/{group}")).json()["invites"] == []


async def test_an_unknown_link_and_a_cancelled_invite(people) -> None:
    ann, bob = await people("ann"), await people("bob")
    group = await _group(ann)
    assert (await bob.get("/api/invites/not-a-real-invite")).status_code == 404
    made = await _invite(ann, group)
    listed = (await ann.get(f"/api/groups/{group}")).json()["invites"]
    assert [i["id"] for i in listed] == [made["id"]]
    # Only through its own group, even for an admin of another.
    other = await _group(ann, "Ann's book club")
    assert (await ann.delete(f"/api/groups/{other}/invites/{made['id']}")).status_code == 404
    assert (await ann.delete(f"/api/groups/{group}/invites/{made['id']}")).status_code == 204
    assert (await bob.post(f"/api/invites/{made['token']}/accept")).status_code == 404


async def test_a_member_cant_use_another_invite(people) -> None:
    ann, bob = await people("ann"), await people("bob")
    group = await _group(ann)
    await _join(bob, ann, group)
    made = await _invite(ann, group, "admin")
    response = await bob.post(f"/api/invites/{made['token']}/accept")
    assert response.status_code == 409
    # Still there for whoever it was meant for.
    assert len((await ann.get(f"/api/groups/{group}")).json()["invites"]) == 1


async def test_accepting_needs_an_account(people, client) -> None:
    ann = await people("ann")
    made = await _invite(ann, await _group(ann))
    assert (await client.post(f"/api/invites/{made['token']}/accept")).status_code == 401


# Roles


async def test_only_a_groups_admins_manage_it(family, people, adb) -> None:
    bob, group = family["bob"], family["group"]
    ann_id = await _user_id(adb, "ann")
    for call in (
        bob.post(f"/api/groups/{group}/invites", json={"role": "view"}),
        bob.patch(f"/api/groups/{group}", json={"name": "Mine"}),
        bob.delete(f"/api/groups/{group}"),
        bob.put(f"/api/groups/{group}/members/{ann_id}", json={"role": "view"}),
        bob.delete(f"/api/groups/{group}/members/{ann_id}"),
    ):
        assert (await call).status_code == 403
    dee = await people("dee")
    assert (await dee.get(f"/api/groups/{group}")).status_code == 404
    assert (await dee.patch(f"/api/groups/{group}", json={"name": "X"})).status_code == 404
    # An invite is waiting, but only admins are shown it.
    await _invite(family["ann"], group)
    shown = (await bob.get(f"/api/groups/{group}")).json()
    assert (shown["role"], shown["invites"]) == ("view", [])
    assert len((await family["ann"].get(f"/api/groups/{group}")).json()["invites"]) == 1


async def test_a_group_keeps_an_admin(family, adb) -> None:
    ann, group = family["ann"], family["group"]
    ann_id, bob_id = await _user_id(adb, "ann"), await _user_id(adb, "bob")
    for call in (
        ann.delete(f"/api/groups/{group}/members/{ann_id}"),
        ann.put(f"/api/groups/{group}/members/{ann_id}", json={"role": "edit"}),
    ):
        response = await call
        assert response.status_code == 409
        assert "needs an admin" in response.json()["detail"]
    promoted = await ann.put(f"/api/groups/{group}/members/{bob_id}", json={"role": "admin"})
    assert promoted.json()["role"] == "admin"
    assert (await ann.delete(f"/api/groups/{group}/members/{ann_id}")).status_code == 204
    assert (await ann.get(f"/api/groups/{group}")).status_code == 404


async def test_anyone_can_leave(family, adb) -> None:
    bob, group = family["bob"], family["group"]
    bob_id = await _user_id(adb, "bob")
    assert (await bob.delete(f"/api/groups/{group}/members/{bob_id}")).status_code == 204
    assert (await bob.get(f"/api/sources/{family['box']}")).status_code == 404


@pytest.mark.parametrize("body", [{"role": "owner"}, {"role": ""}])
async def test_a_bad_role_is_refused(family, body) -> None:
    response = await family["ann"].post(f"/api/groups/{family['group']}/invites", json=body)
    assert response.status_code == 422


# Sharing


async def test_a_viewer_sees_what_is_shared_and_changes_nothing(family) -> None:
    bob, box, stew = family["bob"], family["box"], family["stew"]
    shown = (await bob.get(f"/api/sources/{box}")).json()
    assert (shown["title"], shown["owner_name"], shown["editable"], shown["manageable"]) == (
        "Grandma's Box",
        "ann",
        False,
        False,
    )
    assert [g["name"] for g in shown["shared_with"]] == ["Tetzloff family"]
    assert (await bob.get(f"/api/recipes/{stew}")).json()["editable"] is False
    found = (await bob.get("/api/search", params={"q": "stew"})).json()
    assert [r["title"] for r in found["recipes"]] == ["Stew"]
    body = {"title": "Pie", "ingredients": []}
    assert (await bob.post(f"/api/sources/{box}/recipes", json=body)).status_code == 403
    assert (await bob.put(f"/api/recipes/{stew}", json=body)).status_code == 403
    assert (await bob.delete(f"/api/recipes/{stew}")).status_code == 403
    group = (await bob.get(f"/api/groups/{family['group']}")).json()
    assert [(c["title"], c["owner_name"]) for c in group["collections"]] == [
        ("Grandma's Box", "ann")
    ]


async def test_an_editor_adds_and_changes_recipes_but_not_the_collection(family) -> None:
    cy, box, stew = family["cy"], family["box"], family["stew"]
    assert (await cy.get(f"/api/sources/{box}")).json()["editable"] is True
    added = await cy.post(f"/api/sources/{box}/recipes", json={"title": "Pie", "ingredients": []})
    assert added.status_code == 201, added.text
    changed = await cy.put(f"/api/recipes/{stew}", json={"title": "Stew", "ingredients": ["Kale"]})
    assert changed.status_code == 200, changed.text
    for call in (
        cy.patch(f"/api/sources/{box}/family", json={"title": "Cy's"}),
        cy.delete(f"/api/sources/{box}"),
        cy.put(f"/api/sources/{box}/groups", json={"groups": []}),
    ):
        assert (await call).status_code == 403


async def test_a_group_admin_edits_recipes_too(family, people, adb) -> None:
    ann, bob, group = family["ann"], family["bob"], family["group"]
    bob_id = await _user_id(adb, "bob")
    await ann.put(f"/api/groups/{group}/members/{bob_id}", json={"role": "admin"})
    added = await bob.post(
        f"/api/sources/{family['box']}/recipes", json={"title": "Pie", "ingredients": []}
    )
    assert added.status_code == 201


async def test_unsharing_takes_it_away(family) -> None:
    ann, bob, box = family["ann"], family["bob"], family["box"]
    assert (await ann.put(f"/api/sources/{box}/groups", json={"groups": []})).json() == []
    assert (await bob.get(f"/api/sources/{box}")).status_code == 404
    assert (await bob.get(f"/api/recipes/{family['stew']}")).status_code == 404


async def test_only_groups_youre_in(family, people) -> None:
    dee = await people("dee")
    elsewhere = await _group(dee, "Not Ann's")
    response = await family["ann"].put(
        f"/api/sources/{family['box']}/groups", json={"groups": [family["group"], elsewhere]}
    )
    assert response.status_code == 404
    # Nothing changed.
    shown = (await family["ann"].get(f"/api/sources/{family['box']}")).json()
    assert [g["name"] for g in shown["shared_with"]] == ["Tetzloff family"]


async def test_the_owner_sees_every_group_others_only_theirs(family, people) -> None:
    ann, bob, box = family["ann"], family["bob"], family["box"]
    second = await _group(ann, "Ann's book club")
    await ann.put(f"/api/sources/{box}/groups", json={"groups": [family["group"], second]})
    names = lambda c: [g["name"] for g in c["shared_with"]]  # noqa: E731
    assert names((await ann.get(f"/api/sources/{box}")).json()) == [
        "Ann's book club",
        "Tetzloff family",
    ]
    assert names((await bob.get(f"/api/sources/{box}")).json()) == ["Tetzloff family"]


async def test_an_owner_who_leaves_stops_sharing(family, adb) -> None:
    ann, bob, group = family["ann"], family["bob"], family["group"]
    ann_id, bob_id = await _user_id(adb, "ann"), await _user_id(adb, "bob")
    await ann.put(f"/api/groups/{group}/members/{bob_id}", json={"role": "admin"})
    await ann.delete(f"/api/groups/{group}/members/{ann_id}")
    assert (await bob.get(f"/api/sources/{family['box']}")).status_code == 404
    assert (await bob.get(f"/api/groups/{group}")).json()["collections"] == []


async def test_a_removed_member_loses_it(family, adb) -> None:
    ann, bob, group = family["ann"], family["bob"], family["group"]
    bob_id = await _user_id(adb, "bob")
    assert (await ann.delete(f"/api/groups/{group}/members/{bob_id}")).status_code == 204
    assert (await bob.get(f"/api/sources/{family['box']}")).status_code == 404


async def test_deleting_a_group_keeps_the_collections(family, adb) -> None:
    ann, bob, group = family["ann"], family["bob"], family["group"]
    assert (await ann.delete(f"/api/groups/{group}")).status_code == 204
    assert (await bob.get(f"/api/sources/{family['box']}")).status_code == 404
    assert (await ann.get(f"/api/sources/{family['box']}")).status_code == 200
    assert await adb.scalar(text("SELECT count(*) FROM source_groups")) == 0


async def test_only_a_family_collection_can_be_shared(family, adb) -> None:
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Pink Cake') RETURNING id"))
    with pytest.raises(Exception, match="fk_source_groups_source_id_kind_sources"):
        async with adb.begin_nested():
            await adb.execute(
                text("INSERT INTO source_groups (source_id, group_id) VALUES (:s, :g)"),
                {"s": book, "g": uuid.UUID(family["group"])},
            )
    with pytest.raises(Exception, match="ck_source_groups_family_only"):
        async with adb.begin_nested():
            await adb.execute(
                text(
                    "INSERT INTO source_groups (source_id, kind, group_id) VALUES (:s, 'book', :g)"
                ),
                {"s": book, "g": uuid.UUID(family["group"])},
            )


@pytest.mark.parametrize(
    ("sql", "refused_by"),
    [
        ("INSERT INTO groups (name) VALUES ('')", "ck_groups_name_not_empty"),
        (
            "INSERT INTO group_members (group_id, user_id, role) VALUES (:g, :u, 'owner')",
            "ck_group_members_role_known",
        ),
        (
            "INSERT INTO group_invites (group_id, token_hash, role, expires_at)"
            " VALUES (:g, 'short', 'view', now() + interval '1 day')",
            "ck_group_invites_token_hash_is_sha256",
        ),
        (
            "INSERT INTO group_invites (group_id, token_hash, role, expires_at)"
            " VALUES (:g, sha256('x'), 'view', now() - interval '1 day')",
            "ck_group_invites_expires_after_created",
        ),
        (
            "INSERT INTO group_invites (group_id, token_hash, role, expires_at, used_by)"
            " VALUES (:g, sha256('y'), 'view', now() + interval '1 day', :u)",
            "ck_group_invites_used_by_when_used",
        ),
    ],
)
async def test_the_database_refuses(family, adb, sql, refused_by) -> None:
    dee = await adb.scalar(
        text("INSERT INTO users (issuer, subject) VALUES ('test', 'dee') RETURNING id")
    )
    with pytest.raises(Exception, match=refused_by):
        async with adb.begin_nested():
            await adb.execute(text(sql), {"g": uuid.UUID(family["group"]), "u": dee})
