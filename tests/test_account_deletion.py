"""Deleting an account (account_deletion.py): what goes, what stays, and
who a group passes to."""

from sqlalchemy import text


async def _scalar(adb, sql: str, **params):
    return await adb.scalar(text(sql), params)


async def _user(adb, name: str):
    return await _scalar(adb, "SELECT id FROM users WHERE display_name = :n", n=name)


async def _group(adb, name: str, members: list[tuple[str, str]]):
    group = await _scalar(adb, "INSERT INTO groups (name) VALUES (:n) RETURNING id", n=name)
    for i, (who, role) in enumerate(members):
        await adb.execute(
            text(
                "INSERT INTO group_members (group_id, user_id, role, created_at)"
                " VALUES (:g, :u, :r, now() + make_interval(secs => :i))"
            ),
            {"g": group, "u": await _user(adb, who), "r": role, "i": i},
        )
    return group


async def test_what_goes_and_what_stays(people, client, adb) -> None:
    ann = await people("ann", role="contributor")
    mo, bo, _cy = (
        await people("mo", role="moderator"),
        await people("bo"),
        await people("cy"),
    )
    ann_id = await _user(adb, "ann")

    # Private: a family collection, with its history.
    box = (
        await ann.post("/api/sources/family", json={"title": "Gran's Box", "acknowledged": True})
    ).json()["id"]
    await ann.post(f"/api/sources/{box}/recipes", json={"title": "Fudge", "ingredients": ["salt"]})
    assert await _scalar(adb, "SELECT count(*) FROM revisions WHERE source_id = :s", s=box)

    # The catalog: a published recipe stays; one still waiting goes.
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty"})).json()["id"]
    edition = str(await _scalar(adb, "SELECT id FROM editions WHERE source_id = :s", s=book))
    made = await ann.post(
        f"/api/sources/{book}/recipes",
        json={"title": "Waiting Stew", "editions": [{"edition_id": edition, "page": "3"}]},
    )
    assert made.status_code == 201, made.text
    waiting = made.json()["id"]
    published = await _scalar(
        adb,
        "INSERT INTO recipes (source_id, title, created_by) VALUES (:s, 'Ann''s Soup', :u)"
        " RETURNING id",
        s=book,
        u=ann_id,
    )

    # Groups: one passes to its longest-standing member; one with nobody else goes.
    shared = await _group(adb, "Family", [("ann", "admin"), ("cy", "view"), ("bo", "edit")])
    alone = await _group(adb, "Just Me", [("ann", "admin")])
    larder = await _scalar(
        adb,
        "INSERT INTO larder_lists (owner_id, name) VALUES (:u, 'Pantry') RETURNING id",
        u=ann_id,
    )
    request = await _scalar(
        adb,
        "INSERT INTO book_requests (title, requested_by) VALUES ('Jerusalem', :u) RETURNING id",
        u=ann_id,
    )
    await adb.execute(
        text("INSERT INTO request_votes (request_id, voter) VALUES (:r, :v)"),
        {"r": request, "v": f"user:{ann_id}"},
    )
    await adb.commit()

    bad = await ann.post("/api/account/delete", json={"confirm": "bob"})
    assert bad.status_code == 422 and "ann" in bad.json()["detail"]
    r = await ann.post("/api/account/delete", json={"confirm": "Ann"})
    assert r.status_code == 204, r.text
    assert "openlarder_session" in r.headers.get("set-cookie", "")

    assert (await ann.get("/api/auth/me")).status_code == 401
    assert await _user(adb, "ann") is None
    # Private things and their history are gone.
    assert await _scalar(adb, "SELECT count(*) FROM sources WHERE id = :s", s=box) == 0
    assert await _scalar(adb, "SELECT count(*) FROM revisions WHERE source_id = :s", s=box) == 0
    assert await _scalar(adb, "SELECT count(*) FROM larder_lists WHERE id = :l", l=larder) == 0
    assert await _scalar(adb, "SELECT count(*) FROM recipes WHERE id = :r", r=waiting) == 0
    assert await _scalar(adb, "SELECT count(*) FROM request_votes") == 0
    # What was given to the catalog stays, without its name.
    assert await _scalar(adb, "SELECT created_by FROM recipes WHERE id = :r", r=published) is None
    assert await _scalar(adb, "SELECT title FROM book_requests WHERE id = :r", r=request)
    # The longest-standing member is the group's admin now.
    roles = dict(
        (
            await adb.execute(
                text(
                    "SELECT u.display_name, m.role FROM group_members m"
                    " JOIN users u ON u.id = m.user_id WHERE m.group_id = :g"
                ),
                {"g": shared},
            )
        ).all()
    )
    assert roles == {"cy": "admin", "bo": "edit"}
    assert await _scalar(adb, "SELECT count(*) FROM groups WHERE id = :g", g=alone) == 0
    # The name is free again.
    assert (
        await bo.put("/api/account/display-name", json={"display_name": "ann"})
    ).status_code == 200


async def test_the_owner_hands_it_on_first(people) -> None:
    own = await people("own", role="owner")
    r = await own.post("/api/account/delete", json={"confirm": "own"})
    assert r.status_code == 409 and "owner" in r.json()["detail"]
    assert (await own.get("/api/auth/me")).status_code == 200


async def test_signed_out_deletes_nothing(client) -> None:
    r = await client.post("/api/account/delete", json={"confirm": "delete"})
    assert r.status_code == 401
