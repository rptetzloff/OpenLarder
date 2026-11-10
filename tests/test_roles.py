"""Roles (roles.py): what each may do, and who may give them."""

import pytest
from sqlalchemy import text

from openlarder import roles


def test_the_ladder() -> None:
    assert roles.grantable("user") == roles.grantable("contributor") == []
    assert roles.grantable("moderator") == ["user", "contributor"]
    assert roles.grantable("admin") == ["user", "contributor", "moderator"]
    assert roles.grantable("owner") == ["user", "contributor", "moderator", "admin"]


async def test_me_says_what_a_role_may_do(people) -> None:
    expect = {
        "user": (False, False, False, []),
        "contributor": (False, False, True, []),
        "moderator": (True, False, True, ["user", "contributor"]),
        "admin": (True, True, True, ["user", "contributor", "moderator"]),
    }
    for role, (edit, run, claim, grants) in expect.items():
        me = (await (await people(f"p-{role}", role=role)).get("/api/auth/me")).json()
        assert me["role"] == role
        assert (me["may_edit"], me["may_run"], me["may_claim"], me["grants"]) == (
            edit,
            run,
            claim,
            grants,
        )


async def test_moderators_edit_the_catalog_and_admins_run_the_site(people) -> None:
    con, mo, ad = (
        await people("con", role="contributor"),
        await people("mo", role="moderator"),
        await people("ad", role="admin"),
    )
    book = {"title": "Plenty", "authors": ["Yotam Ottolenghi"]}
    assert (await con.post("/api/sources/manual", json=book)).status_code == 403
    assert (await mo.post("/api/sources/manual", json=book)).status_code == 200
    for path in ("/api/import/runs", "/api/admin/api-usage", "/api/admin/clicks"):
        assert (await mo.get(path)).status_code == 403, path
        assert (await ad.get(path)).status_code == 200, path
    assert (await mo.get("/api/flags?scope=all")).status_code == 200


async def _id(adb, name):
    return await adb.scalar(text("SELECT id FROM users WHERE display_name = :n"), {"n": name})


@pytest.mark.parametrize(
    ("giver", "target_role", "new_role", "ok"),
    [
        ("moderator", "user", "contributor", True),
        ("moderator", "contributor", "user", True),
        ("moderator", "user", "moderator", False),
        ("moderator", "moderator", "user", False),
        ("admin", "user", "moderator", True),
        ("admin", "moderator", "contributor", True),
        ("admin", "user", "admin", False),
        ("admin", "admin", "user", False),
        ("owner", "user", "admin", True),
        ("owner", "admin", "moderator", True),
        ("owner", "user", "owner", False),
        ("contributor", "user", "contributor", False),
    ],
)
async def test_a_role_is_given_only_below_your_own(
    people, adb, giver, target_role, new_role, ok
) -> None:
    g = await people("giver", role=giver)
    await people("them", role=target_role)
    r = await g.put(f"/api/admin/people/{await _id(adb, 'them')}/role", json={"role": new_role})
    assert r.status_code == (200 if ok else 403), r.text
    stored = await adb.scalar(text("SELECT role FROM users WHERE display_name = 'them'"))
    assert stored == (new_role if ok else target_role)


async def test_the_owner_is_never_changed_from_the_site(people, adb) -> None:
    own = await people("own", role="owner")
    await people("own2", role="owner")
    r = await own.put(f"/api/admin/people/{await _id(adb, 'own2')}/role", json={"role": "user"})
    assert r.status_code == 403 and "database" in r.json()["detail"]
    r = await own.put(f"/api/admin/people/{await _id(adb, 'own')}/role", json={"role": "admin"})
    assert r.status_code == 403 and "own role" in r.json()["detail"]


async def test_people_are_listed_highest_first_and_found_by_name(people) -> None:
    mo = await people("mo", role="moderator")
    for name, role in [("ann", "user"), ("cy", "contributor"), ("ad", "admin")]:
        await people(name, role=role)
    listed = (await mo.get("/api/admin/people")).json()
    assert [(p["name"], p["role"], p["changeable"]) for p in listed] == [
        ("ad", "admin", False),
        ("mo", "moderator", False),
        ("cy", "contributor", True),
    ]
    found = (await mo.get("/api/admin/people?q=AN")).json()
    assert [(p["name"], p["changeable"]) for p in found] == [("ann", True)]
    only = (await mo.get("/api/admin/people?role=contributor")).json()
    assert [p["name"] for p in only] == ["cy"]
    assert (await (await people("bo")).get("/api/admin/people")).status_code == 403


def test_the_migration_keeps_admins_and_makes_enterers_contributors(alembic_config, engine) -> None:
    from alembic import command

    command.downgrade(alembic_config, "0038")
    try:
        with engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO users (issuer, subject, display_name, is_admin, is_enterer) VALUES"
                    " ('m', 'a', 'mig-admin', true, false), ('m', 'e', 'mig-ent', false, true),"
                    " ('m', 'u', 'mig-user', false, false)"
                )
            )
        command.upgrade(alembic_config, "head")
        with engine.begin() as c:
            got = dict(
                c.execute(text("SELECT display_name, role FROM users WHERE issuer = 'm'")).all()
            )
            c.execute(text("DELETE FROM users WHERE issuer = 'm'"))
        assert got == {"mig-admin": "admin", "mig-ent": "contributor", "mig-user": "user"}
    finally:
        command.upgrade(alembic_config, "head")
