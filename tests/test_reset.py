"""Emptying the catalog (reset.py): what goes, what stays."""

from sqlalchemy import text

from openlarder import reset


async def _tables(adb) -> set[str]:
    rows = await adb.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    return set(rows)


async def test_every_table_is_either_emptied_or_kept(adb) -> None:
    """A new table has to be decided on here, so the reset never misses one."""
    lists = (set(reset.CATALOG), set(reset.PEOPLE), set(reset.KEPT))
    assert await _tables(adb) == set().union(*lists)
    assert sum(len(x) for x in lists) == len(set().union(*lists))


async def test_nothing_kept_points_into_the_catalog_but_a_requests_book(adb) -> None:
    """TRUNCATE refuses a table a kept one points at; the one such link is
    let go for the length of the reset."""
    links = await adb.execute(
        text(
            "SELECT conrelid::regclass::text, conname FROM pg_constraint"
            " WHERE contype = 'f' AND confrelid::regclass::text = ANY(:catalog)"
            " AND NOT conrelid::regclass::text = ANY(:catalog)"
        ),
        {"catalog": list(reset.CATALOG)},
    )
    assert links.all() == [("book_requests", "fk_book_requests_source_id_sources")]
    # Nothing never emptied points at anything emptied, for --everything,
    # but a shop at whoever last changed it: let go the same way.
    kept = await adb.execute(
        text(
            "SELECT conrelid::regclass::text, conname FROM pg_constraint"
            " WHERE contype = 'f' AND conrelid::regclass::text = ANY(:kept)"
            " AND NOT confrelid::regclass::text = ANY(:kept)"
        ),
        {"kept": list(reset.KEPT)},
    )
    assert kept.all() == [("shops", "fk_shops_updated_by_users")]


async def test_the_catalog_goes_and_the_rest_stays(people, adb) -> None:
    ann = await people("ann")
    owner = await adb.scalar(text("SELECT id FROM users WHERE display_name = 'ann'"))
    # A request for the book, before it's here: kept, unlinked.
    await ann.post("/api/requests", json={"title": "Plenty"})
    book = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Plenty') RETURNING id"))
    await adb.execute(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:b, '9780393541113')"), {"b": book}
    )
    recipe = await adb.scalar(
        text("INSERT INTO recipes (source_id, title) VALUES (:b, 'Shakshuka') RETURNING id"),
        {"b": book},
    )
    await adb.execute(
        text(
            "INSERT INTO recipe_ingredients (recipe_id, position, original_text)"
            " VALUES (:r, 1, 'Eggs')"
        ),
        {"r": recipe},
    )
    eggs = await adb.scalar(
        text("INSERT INTO ingredients (name, match_key) VALUES ('Eggs', 'egg') RETURNING id")
    )
    tag = await adb.scalar(text("SELECT id FROM tags LIMIT 1"))
    await adb.execute(
        text("INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (:r, :t)"), {"r": recipe, "t": tag}
    )
    # What the recipe needs goes with it; the equipment list stays.
    need = await adb.scalar(
        text("INSERT INTO recipe_equipment (recipe_id, position) VALUES (:r, 1) RETURNING id"),
        {"r": recipe},
    )
    await adb.execute(
        text(
            "INSERT INTO equipment_options (recipe_equipment_id, recipe_id, rank, equipment_id)"
            " SELECT :n, :r, 1, id FROM equipment WHERE name = 'Dutch oven'"
        ),
        {"n": need, "r": recipe},
    )
    # A family collection goes too (Ray, 2026-11-10).
    await adb.execute(
        text(
            "INSERT INTO sources (title, kind, private, owner_id, acknowledged_at)"
            " VALUES ('Nana''s Cards', 'family', true, :o, now())"
        ),
        {"o": owner},
    )
    # A larder: its items go, the list stays.
    larder = (await ann.post("/api/larder/lists", json={"name": "Pantry"})).json()["id"]
    await adb.execute(
        text("INSERT INTO larder_items (list_id, ingredient_id, name) VALUES (:l, :i, 'Eggs')"),
        {"l": larder, "i": eggs},
    )
    # Their equipment: the equipment list stays, so what they have of it does.
    kitchen = (await ann.post("/api/equipment-lists/lists", json={"name": "Kitchen"})).json()["id"]
    wok = await ann.post(f"/api/equipment-lists/lists/{kitchen}/items", json={"name": "Wok"})
    assert wok.json()["equipment"] == "Wok"
    assert await adb.scalar(text("SELECT source_id FROM book_requests")) == book
    tags_before = await adb.scalar(text("SELECT count(*) FROM tags"))
    listed = [
        await adb.scalar(text(f"SELECT count(*) FROM {table}"))
        for table in ("equipment", "equipment_aliases", "equipment_counts_as")
    ]
    assert all(listed), listed
    assert await adb.scalar(text("SELECT count(*) FROM revisions WHERE table_name = 'sources'"))

    found = await reset.counts(adb)
    assert (found["sources"], found["recipes"], found["larder_items"]) == (2, 1, 1)
    await reset.reset(adb)

    for table in reset.CATALOG:
        assert await adb.scalar(text(f"SELECT count(*) FROM {table}")) == 0, table
    assert await adb.scalar(text("SELECT count(*) FROM revisions WHERE table_name <> 'tags'")) == 0
    assert await adb.scalar(text("SELECT count(*) FROM tags")) == tags_before
    assert listed == [
        await adb.scalar(text(f"SELECT count(*) FROM {table}"))
        for table in ("equipment", "equipment_aliases", "equipment_counts_as")
    ]
    assert await adb.scalar(text("SELECT count(*) FROM users")) >= 1
    assert await adb.scalar(text("SELECT count(*) FROM larder_lists")) == 1
    assert (
        await adb.scalar(
            text("SELECT count(*) FROM equipment_list_items WHERE equipment_id IS NOT NULL")
        )
        == 1
    )
    assert (await adb.execute(text("SELECT status, source_id FROM book_requests"))).one() == (
        "open",
        None,
    )
    # The request's link to its book is back, and links again as it returns.
    again = await adb.scalar(text("INSERT INTO sources (title) VALUES ('Plenty') RETURNING id"))
    await adb.execute(
        text("INSERT INTO editions (source_id, isbn13) VALUES (:b, '9780393541113')"), {"b": again}
    )
    assert await adb.scalar(text("SELECT source_id FROM book_requests")) == again
    assert (
        await adb.scalar(
            text(
                "SELECT count(*) FROM pg_constraint"
                " WHERE conname = 'fk_book_requests_source_id_sources'"
            )
        )
        == 1
    )


async def test_everything_leaves_only_the_tag_list(people, adb) -> None:
    ann = await people("ann")
    await ann.post("/api/requests", json={"title": "Plenty"})
    await ann.post("/api/larder/lists", json={"name": "Pantry"})
    kitchen = (await ann.post("/api/equipment-lists/lists", json={"name": "Kitchen"})).json()["id"]
    await ann.post(f"/api/equipment-lists/lists/{kitchen}/items", json={"name": "Wok"})
    await adb.execute(text("INSERT INTO sources (title) VALUES ('Plenty')"))
    await adb.execute(
        text(
            "UPDATE shops SET affiliate_id = '777', enabled = true, updated_by ="
            " (SELECT id FROM users WHERE display_name = 'ann')"
            " WHERE kind = 'bookseller' AND key = 'bookshop'"
        )
    )
    tags_before = await adb.scalar(text("SELECT count(*) FROM tags"))
    found = await reset.counts(adb, everything=True)
    assert (found["users"], found["book_requests"], found["larder_lists"]) == (1, 1, 1)
    assert (found["equipment_lists"], found["equipment_list_items"]) == (1, 1)

    await reset.reset(adb, everything=True)

    for table in reset.CATALOG + reset.PEOPLE:
        assert await adb.scalar(text(f"SELECT count(*) FROM {table}")) == 0, table
    assert await adb.scalar(text("SELECT count(*) FROM tags")) == tags_before
    # The shops stay as they were set, without who set them; and the link
    # to an account is there again for the next to change one.
    kept = (
        await adb.execute(
            text(
                "SELECT affiliate_id, enabled, updated_by FROM shops"
                " WHERE kind = 'bookseller' AND key = 'bookshop'"
            )
        )
    ).one()
    assert tuple(kept) == ("777", True, None)
    assert await adb.scalar(text("SELECT count(*) FROM shops")) == 9
    link = await adb.scalar(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conname = 'fk_shops_updated_by_users'"
        )
    )
    assert link == "FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL"
    assert await adb.scalar(text("SELECT count(*) FROM alembic_version")) == 1
