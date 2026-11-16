"""The import's Equipment column (importer.py), treated as its Ingredients
column is (*Ray, 2026-11-16*): read as a row of a whole book reads its
cell, what saving would refuse left out and flagged, given to a recipe
already there when the import runs again, and a thing that isn't in the
equipment list flagged when it's spelt like one that is, with a one-click
change.

The CSV here is made up; the private files are never used as fixtures."""

import pytest
from sqlalchemy import text

from openlarder import importer, typos
from openlarder.ingredients import match_key
from test_import import _item, admin, pink_cake  # noqa: F401

RECIPES_CSV = (
    "Source,Recipe Name,Pg #,Ingredients,Equipment\n"
    'Pink Cake,Rhubarb Cake,112,Rhubarb; Egg,"stand mixer or hand mixer; 9-inch springform pan"\n'
    "Pink Cake,Toast,3,Bread,none\n"
    "Pink Cake,Plain Sponge,5,Flour,\n"
    'Pink Cake,Waffles,9,Egg,"waffle iron\nwok, kitchen scale"\n'
)
BOWL = "“Mixing bowl” is expected in any kitchen, so it isn't recorded."
NINE = "“9-inch” is a size. Name what it's the size of, like “9-inch cake pan”."


# Reading the list


def test_the_equipment_column_is_read_as_written() -> None:
    rows = importer.parse_recipes(RECIPES_CSV).rows
    assert [(r.title, r.equipment) for r in rows] == [
        ("Rhubarb Cake", "stand mixer or hand mixer; 9-inch springform pan"),
        ("Toast", "none"),
        ("Plain Sponge", ""),
        # A new line in a cell parts two needs, so the cell isn't squashed.
        ("Waffles", "waffle iron\nwok, kitchen scale"),
    ]


def test_a_list_without_the_column_says_nothing_of_equipment() -> None:
    rows = importer.parse_recipes("Source,Recipe Name,Pg #,Ingredients\nA,B,1,Egg\n").rows
    assert [r.equipment for r in rows] == [""]


async def test_parse_passes_each_rows_equipment_on(admin) -> None:  # noqa: F811
    books = "Source Title,Author(s),ISBN,Year Published\nPink Cake,Jo Baker,,\n"
    parsed = await admin.post(
        "/api/import/parse", json={"books_csv": books, "recipes_csv": RECIPES_CSV}
    )
    assert [r["equipment"] for r in parsed.json()["recipes"]] == [
        "stand mixer or hand mixer; 9-inch springform pan",
        "none",
        "",
        "waffle iron\nwok, kitchen scale",
    ]


# Storing it


async def _needs(adb, title: str) -> tuple[bool, list[str]]:
    """Whether a recipe's equipment is recorded, and each need as "size:
    thing or thing", in order."""
    checked = await adb.scalar(
        text("SELECT equipment_checked FROM recipes WHERE title = :t"), {"t": title}
    )
    rows = await adb.execute(
        text(
            "SELECT coalesce(n.detail, '') || ': ' || string_agg(e.name, ' or ' ORDER BY o.rank)"
            " FROM recipe_equipment n"
            " JOIN recipes r ON r.id = n.recipe_id"
            " JOIN equipment_options o ON o.recipe_equipment_id = n.id"
            " JOIN equipment e ON e.id = o.equipment_id"
            " WHERE r.title = :t GROUP BY n.id, n.position, n.detail ORDER BY n.position"
        ),
        {"t": title},
    )
    return checked, [row[0] for row in rows]


async def _send(admin, *items) -> dict:  # noqa: F811
    sent = await admin.post("/api/import/recipes", json={"items": list(items)})
    assert sent.status_code == 200, sent.text
    return sent.json()


def _flags(result: dict) -> list[tuple[int, str, str | None]]:
    return sorted((f["row"], f["kind"], f["detail"]) for f in result["flags"])


async def test_a_rows_equipment_is_stored_in_its_three_states(admin, pink_cake, adb) -> None:  # noqa: F811
    result = await _send(
        admin,
        _item(pink_cake, equipment="stand mixer or hand mixer; 9-inch springform pan"),
        _item(pink_cake, row=3, title="Toast", page="3", equipment=" None "),
        _item(pink_cake, row=4, title="Plain Sponge", page="5", equipment=""),
        _item(pink_cake, row=5, title="Waffles", page="9"),
        _item(pink_cake, row=6, title="Stir-Fry", page="11", equipment="wok\nkitchen scale, wok"),
    )
    assert (result["created"], result["errors"], result["flags"]) == (5, [], [])
    assert await _needs(adb, "Rhubarb Cake") == (
        True,
        [": Stand mixer or Hand mixer", "9-inch: Springform pan"],
    )
    # "none" is nothing special; an empty cell, or none sent, is not recorded.
    assert await _needs(adb, "Toast") == (True, [])
    assert await _needs(adb, "Plain Sponge") == (False, [])
    assert await _needs(adb, "Waffles") == (False, [])
    # A new line and a comma part needs too, and a need is kept once.
    assert await _needs(adb, "Stir-Fry") == (True, [": Wok", ": Kitchen scale"])


async def test_what_saving_would_refuse_is_left_out_and_flagged(admin, pink_cake, adb) -> None:  # noqa: F811
    """As a line with an amount is: the rest of the row is still worth having."""
    result = await _send(
        admin,
        _item(pink_cake, equipment="mixing bowl; wok; 9-inch; stand mixer or bowl"),
        _item(pink_cake, row=3, title="Toast", page="3", equipment="bowl, whisk"),
        _item(pink_cake, row=4, title="Stir-Fry", page="11", equipment="none; wok"),
    )
    assert (result["created"], result["errors"]) == (3, [])
    whisk = "“Whisk” is expected in any kitchen, so it isn't recorded."
    assert _flags(result) == sorted(
        [
            (2, "equipment_removed", BOWL),
            (2, "equipment_removed", NINE),
            # A need with a choice goes whole when one of its things is refused.
            (2, "equipment_removed", BOWL),
            (3, "equipment_removed", BOWL),
            (3, "equipment_removed", whisk),
            (
                4,
                "equipment_removed",
                "“none” is for a recipe that needs nothing special. Take it out, or the"
                " equipment beside it.",
            ),
        ]
    )
    assert await _needs(adb, "Rhubarb Cake") == (True, [": Wok"])
    # Only what any kitchen has: nothing kept, and not said to need nothing.
    assert await _needs(adb, "Toast") == (False, [])
    # "none" beside equipment: the equipment is kept.
    assert await _needs(adb, "Stir-Fry") == (True, [": Wok"])
    flagged = await adb.scalar(
        text("SELECT count(*) FROM recipe_flags WHERE kind = 'equipment_removed'")
    )
    assert flagged == 6
    # Nothing any kitchen has was made a thing of.
    assert await adb.scalar(text("SELECT count(*) FROM equipment WHERE NOT listed")) == 0


async def test_a_name_the_list_doesnt_have_comes_in_with_its_recipe(admin, pink_cake, adb) -> None:  # noqa: F811
    await _send(admin, _item(pink_cake, equipment="egg coddler"))
    assert await _needs(adb, "Rhubarb Cake") == (True, [": Egg coddler"])
    assert (
        await adb.scalar(text("SELECT listed FROM equipment WHERE name = 'Egg coddler'")) is False
    )


async def test_running_again_gives_a_recipe_its_equipment_once(admin, pink_cake, adb) -> None:  # noqa: F811
    """As a chapter is filled in: a recipe imported before the list had the
    column gets its equipment on the next run, and what's recorded since is
    left alone."""
    await _send(admin, _item(pink_cake), _item(pink_cake, row=3, title="Toast", page="3"))
    assert await _needs(adb, "Rhubarb Cake") == (False, [])
    again = [
        _item(pink_cake, equipment="wok; mixing bowl"),
        _item(pink_cake, row=3, title="Toast", page="3", equipment="none"),
    ]
    result = await _send(admin, *again)
    assert (result["created"], result["skipped"]) == (0, 2)
    assert _flags(result) == [(2, "equipment_removed", BOWL)]
    assert await _needs(adb, "Rhubarb Cake") == (True, [": Wok"])
    assert await _needs(adb, "Toast") == (True, [])
    # A third run, with other equipment in the list: what's recorded stays,
    # and nothing is flagged again.
    third = [
        _item(pink_cake, equipment="blender; mixing bowl"),
        _item(pink_cake, row=3, title="Toast", page="3", equipment="wok"),
    ]
    result = await _send(admin, *third)
    assert (result["skipped"], result["flags"]) == (2, [])
    assert await _needs(adb, "Rhubarb Cake") == (True, [": Wok"])
    assert await _needs(adb, "Toast") == (True, [])
    assert await adb.scalar(text("SELECT count(*) FROM recipe_flags")) == 1


async def test_a_refused_need_isnt_flagged_twice_on_a_recipe_left_unrecorded(
    admin,  # noqa: F811
    pink_cake,  # noqa: F811
    adb,
) -> None:
    """Only what any kitchen has: the recipe stays not recorded, so every
    run reads its cell again. It's flagged the first time only."""
    item = _item(pink_cake, equipment="mixing bowl")
    assert _flags(await _send(admin, item)) == [(2, "equipment_removed", BOWL)]
    assert (await _send(admin, item))["flags"] == []
    assert await adb.scalar(text("SELECT count(*) FROM recipe_flags")) == 1


# Equipment that isn't in the list, spelt like something that is


@pytest.mark.parametrize(
    ("written", "listed"),
    [
        ("Wafle iron", "Waffle iron"),
        ("Springfrom pan", "Springform pan"),
        ("Imersion blender", "Immersion blender"),
        ("Presure cooker", "Pressure cooker"),
    ],
)
def test_equipment_spelt_like_something_in_the_list(written, listed) -> None:
    assert typos.spelt_like(match_key(written), match_key(listed))


@pytest.mark.parametrize(
    ("written", "listed"),
    [
        # Another thing, not another spelling.
        ("Tart ring", "Tart pan"),
        ("Rice cooker", "Slow cooker"),
        # More words, or fewer.
        ("Mini waffle iron", "Waffle iron"),
        # One letter off in a short word.
        ("Woks", "Wok"),
        ("Wak", "Wok"),
    ],
)
def test_equipment_that_isnt(written, listed) -> None:
    assert match_key(written) == match_key(listed) or not typos.spelt_like(
        match_key(written), match_key(listed)
    )


async def _run(admin, *batches) -> list[tuple[str, str, str]]:  # noqa: F811
    """An import run as the page sends it; what its finish flags as typos,
    as (kind, recipe, detail)."""
    run = (
        await admin.post(
            "/api/import/runs",
            json={"books_in_list": 1, "recipes_in_file": sum(len(b) for b in batches)},
        )
    ).json()["id"]
    for batch in batches:
        sent = await admin.post("/api/import/recipes", json={"items": batch, "run_id": run})
        assert sent.status_code == 200, sent.text
    done = await admin.post(
        f"/api/import/runs/{run}/finish",
        json={"books_added": 0, "books_existing": 1, "books_failed": 0},
    )
    assert done.status_code == 200, done.text
    return [(t["kind"], t["recipe"], t["detail"]) for t in done.json()["typos"]]


async def _open(admin) -> list[dict]:  # noqa: F811
    page = await admin.get("/api/flags?scope=all&state=open&kind=equipment_typo")
    return page.json()["flags"]


async def test_a_run_flags_misspelt_equipment_and_one_click_fixes_it(admin, pink_cake, adb) -> None:  # noqa: F811
    batch = [
        _item(pink_cake, equipment="8-inch wafle iron or wok; stand mixer"),
        # By another name for something in the list ("Waffle maker").
        _item(pink_cake, row=3, title="Toast", page="3", equipment="wafle maker"),
        # In the list, and new with nothing like it: neither is flagged.
        _item(pink_cake, row=4, title="Stir-Fry", page="11", equipment="wok; egg coddler"),
    ]
    # In the order of the recipes' ids, which is no order: sorted here.
    assert sorted(await _run(admin, batch)) == [
        ("equipment_typo", "Rhubarb Cake", "Wafle iron → Waffle iron"),
        ("equipment_typo", "Toast", "Wafle maker → Waffle iron"),
    ]
    flags = {f["recipe"]["title"]: f for f in await _open(admin)}
    assert sorted(flags) == ["Rhubarb Cake", "Toast"]

    fixed = await admin.post(f"/api/flags/{flags['Rhubarb Cake']['id']}/apply")
    assert fixed.status_code == 200, fixed.text
    assert (fixed.json()["resolution"], fixed.json()["note"]) == (
        "fixed",
        "Changed to “Waffle iron”.",
    )
    # The need is of the thing in the list now, its size and its other
    # choice as they were, and the rest of the recipe's needs with it.
    assert await _needs(adb, "Rhubarb Cake") == (
        True,
        ["8-inch: Waffle iron or Wok", ": Stand mixer"],
    )
    # The misspelt thing goes when no recipe needs it any more.
    gone = "SELECT count(*) FROM equipment WHERE name = :n"
    assert await adb.scalar(text(gone), {"n": "Wafle iron"}) == 0
    assert await adb.scalar(text(gone), {"n": "Wafle maker"}) == 1
    assert (await admin.post(f"/api/flags/{flags['Rhubarb Cake']['id']}/apply")).status_code == 409
    # In the run's history, by what it is.
    [run] = (await admin.get("/api/import/runs")).json()
    assert run["flags_raised"] == 2
    report = (await admin.get(f"/api/import/runs/{run['id']}/report.csv")).text
    assert '"equipment typo","Wafle maker → Waffle iron"' in report


async def test_a_dismissed_equipment_typo_isnt_flagged_again(admin, pink_cake) -> None:  # noqa: F811
    batch = [_item(pink_cake, equipment="wafle iron")]
    await _run(admin, batch)
    [flag] = await _open(admin)
    dismissed = await admin.post(
        f"/api/flags/{flag['id']}/resolve",
        json={"resolution": "dismissed", "note": "The book's own spelling."},
    )
    assert dismissed.status_code == 200
    assert await _run(admin, [_item(pink_cake, row=3, title="Toast", page="3")]) == []


async def test_what_any_kitchen_has_is_never_suggested(admin, pink_cake) -> None:  # noqa: F811
    """ "Colandar" is spelt like "Colander", which no recipe records: taking
    it up would only be refused."""
    assert typos.spelt_like(match_key("Colandar"), match_key("Colander"))
    assert await _run(admin, [_item(pink_cake, equipment="colandar")]) == []


async def test_a_change_that_cant_be_made_says_why(admin, pink_cake, adb) -> None:  # noqa: F811
    await _run(admin, [_item(pink_cake, equipment="wafle iron")])
    [flag] = await _open(admin)
    recipe = flag["recipe"]["id"]
    # Somebody has put the recipe right since.
    edition = await adb.scalar(text("SELECT id FROM editions"))
    body = {
        "title": "Rhubarb Cake",
        "editions": [{"edition_id": str(edition), "page": "112"}],
        "ingredients": ["Rhubarb", "Caster Sugar"],
        "equipment": ["waffle iron"],
    }
    changed = await admin.put(f"/api/recipes/{recipe}", json=body)
    assert changed.status_code == 200, changed.text
    refused = await admin.post(f"/api/flags/{flag['id']}/apply")
    assert refused.status_code == 409
    assert "doesn't need “Wafle iron” now" in refused.json()["detail"]


async def test_only_the_public_catalogs_equipment_is_flagged(admin, pink_cake, adb) -> None:  # noqa: F811
    """As for ingredients: what isn't published isn't compared or flagged."""
    assert len(await _run(admin, [_item(pink_cake, equipment="wafle iron")])) == 1
    # Sent back by a moderator, say: not in the public catalog now.
    await adb.execute(text("UPDATE recipes SET review = 'returned'"))
    await adb.execute(text("DELETE FROM recipe_flags"))
    await adb.commit()
    assert await _run(admin, []) == []
