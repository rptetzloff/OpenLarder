"""Possible typos in ingredient names (typos.py): flagged, never changed
unasked (Ray, 2026-11-10), with a one-click change."""

import pytest
from sqlalchemy import text

from openlarder import typos
from openlarder.ingredients import match_key
from test_import import _item, admin, pink_cake  # noqa: F401

# The household index's own cases, measured (typos.py).


@pytest.mark.parametrize(
    "rare, common, rare_uses, common_uses",
    [
        # Swapped letters, however often the typo is used.
        ("Lemon Jucie", "Lemon Juice", 7, 2043),
        ("Srhimp", "Shrimp", 1, 323),
        ("Daikon Raidsh", "Daikon Radish", 1, 80),
        # One letter off in a long word, used once or twice.
        ("Vanila Extract", "Vanilla Extract", 1, 2025),
        ("Gresh Ginger", "Fresh Ginger", 1, 1230),
        ("Pstry Flour", "Pastry Flour", 1, 82),
        # Two off in a word of 8 or more.
        ("Pistarchios", "Pistachios", 1, 141),
        # A swap is suggested even when it's a real ingredient: a person decides.
        ("Crema", "Cream", 1, 17),
    ],
)
def test_names_that_look_like_typos(rare, common, rare_uses, common_uses) -> None:
    assert typos.close(match_key(rare), match_key(common), rare_uses, common_uses)


@pytest.mark.parametrize(
    "rare, common, rare_uses, common_uses",
    [
        # Both in common use: two ingredients.
        ("Beef", "Beet", 88, 122),
        ("Port", "Pork", 16, 77),
        # One letter off in a short word.
        ("Jam", "Ham", 1, 73),
        ("Malt", "Salt", 1, 59),
        # Not used much more often.
        ("Lardo", "Lard", 1, 3),
        # Two words differ.
        ("Red Wine", "White Rice", 1, 100),
        # More words, not a typo of fewer.
        ("Lemon Juice", "Juice", 1, 100),
    ],
)
def test_names_that_dont(rare, common, rare_uses, common_uses) -> None:
    assert not typos.close(match_key(rare), match_key(common), rare_uses, common_uses)


def test_the_line_is_changed_where_the_option_is_written() -> None:
    assert typos.corrected("Lemon Jucie or Lime Juice", "Lemon Jucie", "Lemon Juice") == (
        "Lemon Juice or Lime Juice"
    )
    # Only a whole option: "Banan" isn't changed inside "Banana Bread".
    assert typos.corrected("Banana Bread", "Banan", "Banana") is None
    assert typos.parse("Lemon Jucie → Lemon Juice") == ("Lemon Jucie", "Lemon Juice")
    assert typos.parse("no arrow") is None


# Importing


async def _run(admin, *batches):  # noqa: F811
    """An import run, batch by batch, as the page sends it; the typos its
    finish flags."""
    run = (
        await admin.post(
            "/api/import/runs",
            json={"books_in_list": 1, "recipes_in_file": sum(len(b) for b in batches)},
        )
    ).json()["id"]
    for batch in batches:
        r = await admin.post("/api/import/recipes", json={"items": batch, "run_id": run})
        assert r.status_code == 200, r.text
    done = await admin.post(
        f"/api/import/runs/{run}/finish",
        json={"books_added": 0, "books_existing": 1, "books_failed": 0},
    )
    assert done.status_code == 200, done.text
    return [(t["book"], t["recipe"], t["detail"]) for t in done.json()["typos"]]


def _many(work, name, first, n=5):
    return [
        _item(work, row=first + i, title=f"{name} {i}", page=str(first + i), ingredients=[name])
        for i in range(n)
    ]


async def _open(admin):  # noqa: F811
    page = await admin.get("/api/flags?scope=all&state=open&kind=possible_typo")
    return page.json()["flags"]


async def test_a_run_flags_a_typo_and_one_click_fixes_it(admin, pink_cake, adb) -> None:  # noqa: F811
    typo = [_item(pink_cake, ingredients=["Rhubarb", "Lemon Jucie"])]
    # The typo comes first, its right spelling in a later batch: caught at
    # the end of the run.
    assert await _run(admin, typo, _many(pink_cake, "Lemon Juice", 10)) == [
        ("Love Is a Pink Cake", "Rhubarb Cake", "Lemon Jucie → Lemon Juice")
    ]
    [flag] = await _open(admin)

    fixed = (await admin.post(f"/api/flags/{flag['id']}/apply")).json()
    assert (fixed["resolution"], fixed["note"]) == ("fixed", "Changed to “Lemon Juice”.")
    recipe = flag["recipe"]["id"]
    assert (
        await adb.scalars(
            text(
                "SELECT original_text FROM recipe_ingredients"
                " WHERE recipe_id = :r ORDER BY position"
            ),
            {"r": recipe},
        )
    ).all() == ["Rhubarb", "Lemon Juice"]
    # Matched to Lemon Juice, and the misspelt ingredient is gone.
    assert (
        await adb.scalar(
            text(
                "SELECT i.name FROM ingredient_options o"
                " JOIN ingredients i ON i.id = o.ingredient_id"
                " JOIN recipe_ingredients l ON l.id = o.recipe_ingredient_id"
                " WHERE l.recipe_id = :r AND l.position = 2"
            ),
            {"r": recipe},
        )
        == "Lemon Juice"
    )
    assert (
        await adb.scalar(text("SELECT count(*) FROM ingredients WHERE name = 'Lemon Jucie'")) == 0
    )
    assert (await admin.post(f"/api/flags/{flag['id']}/apply")).status_code == 409
    # In the run's report too.
    [run] = (await admin.get("/api/import/runs")).json()
    assert run["flags_raised"] >= 1


async def test_a_typo_from_an_earlier_run_is_caught_by_a_later_one(admin, pink_cake) -> None:  # noqa: F811
    await _run(admin, [_item(pink_cake, ingredients=["Rhubarb", "Lemon Jucie"])])
    assert await _open(admin) == []
    assert await _run(admin, _many(pink_cake, "Lemon Juice", 10)) == [
        ("Love Is a Pink Cake", "Rhubarb Cake", "Lemon Jucie → Lemon Juice")
    ]


async def test_a_dismissed_typo_isnt_flagged_again(admin, pink_cake) -> None:  # noqa: F811
    crema = [_item(pink_cake, title="Crema Cake", ingredients=["Crema"])]
    await _run(admin, crema, _many(pink_cake, "Cream", 30))
    [flag] = await _open(admin)
    assert flag["detail"] == "Crema → Cream"
    r = await admin.post(
        f"/api/flags/{flag['id']}/resolve",
        json={"resolution": "dismissed", "note": "Crema is Mexican sour cream."},
    )
    assert r.status_code == 200
    assert await _run(admin, _many(pink_cake, "Cream", 50)) == []


async def test_only_the_public_catalog_is_compared(admin, pink_cake, adb) -> None:  # noqa: F811
    """A family collection's names are its own: not suggested, not flagged."""
    owner = await adb.scalar(text("SELECT id FROM users LIMIT 1"))
    box = await adb.scalar(
        text(
            "INSERT INTO sources (title, kind, private, owner_id, acknowledged_at)"
            " VALUES ('Nana''s Cards', 'family', true, :o, now()) RETURNING id"
        ),
        {"o": owner},
    )
    recipe = await adb.scalar(
        text("INSERT INTO recipes (source_id, title) VALUES (:b, 'Lemonade') RETURNING id"),
        {"b": box},
    )
    line = await adb.scalar(
        text(
            "INSERT INTO recipe_ingredients (recipe_id, position, original_text)"
            " VALUES (:r, 1, 'Lemon Jucie') RETURNING id"
        ),
        {"r": recipe},
    )
    jucie = await adb.scalar(
        text(
            "INSERT INTO ingredients (name, match_key) VALUES ('Lemon Jucie', 'lemon juci')"
            " RETURNING id"
        )
    )
    await adb.execute(
        text(
            "INSERT INTO ingredient_options"
            " (recipe_ingredient_id, recipe_id, rank, name, ingredient_id)"
            " VALUES (:l, :r, 1, 'Lemon Jucie', :i)"
        ),
        {"l": line, "r": recipe, "i": jucie},
    )
    assert await _run(admin, _many(pink_cake, "Lemon Juice", 10)) == []
