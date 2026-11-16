"""The admin overview's numbers (routers/overview.py): how many published
recipes have equipment recorded. The share's wording is tested on
overview.share, without a request; the counting goes through the routes."""

import pytest
from sqlalchemy import text

from openlarder.routers import overview

GET = "/api/admin/overview"


@pytest.mark.parametrize(
    ("part", "whole", "said"),
    [
        (0, 0, ""),
        (0, 40, "0%"),
        (40, 40, "100%"),
        # A half goes up: 12.5% is 13%, and 37.5% is 38%.
        (1, 8, "13%"),
        (3, 8, "38%"),
        (1, 3, "33%"),
        (1, 2, "50%"),
        (2, 3, "67%"),
        # Rounding to a whole number would say none, or all.
        (1, 10_000, "under 1%"),
        (9_999, 10_000, "over 99%"),
        # At the edges exactly, a whole number is true.
        (1, 100, "1%"),
        (99, 100, "99%"),
        # Just inside them, 199 of 200 is 99.5%, which isn't 100%.
        (199, 200, "over 99%"),
        (1, 200, "under 1%"),
    ],
)
def test_a_share_is_never_rounded_to_none_or_all(part: int, whole: int, said: str) -> None:
    assert overview.share(part, whole) == said


async def _recipe(c, book: str, edition: str | None, title: str, **more) -> str:
    body = {"title": title, "ingredients": ["eggs"], **more}
    if edition:
        body["editions"] = [{"edition_id": edition}]
    made = await c.post(f"/api/sources/{book}/recipes", json=body)
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def test_equipment_recorded_counts_what_anyone_can_see(people, client, adb) -> None:
    mo = await people("mo", role="moderator")
    for other in (client, await people("ann"), await people("con", role="contributor")):
        assert (await other.get(GET)).status_code in (401, 403)

    async def now() -> tuple[int, int]:
        said = (await mo.get(GET)).json()["equipment"]
        assert said["share"] == overview.share(said["recorded"], said["recipes"])
        return said["recorded"], said["recipes"]

    # From wherever it starts: the rule is what each recipe adds.
    recorded, recipes = await now()
    book = (await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": []})).json()[
        "id"
    ]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": book})
    )
    # Not recorded: a recipe, and nothing said of its equipment.
    plain = await _recipe(mo, book, edition, "Shakshuka")
    assert await now() == (recorded, recipes + 1)
    # A need listed, and nothing special said: both are recorded.
    fried = await _recipe(mo, book, edition, "Stir-fry", equipment=["wok"])
    await _recipe(mo, book, edition, "Salad", nothing_special=True)
    assert await now() == (recorded + 2, recipes + 3)
    # A need counts though nobody has said the list is whole (as an
    # accepted suggestion will leave it): the recipe's page shows it.
    await adb.execute(
        text("UPDATE recipes SET equipment_checked = false WHERE id = :r"), {"r": fried}
    )
    assert await now() == (recorded + 2, recipes + 3)
    # A recipe waiting for review isn't in the catalog yet.
    con = await people("cy", role="contributor")
    waiting = await _recipe(con, book, edition, "Waiting Pie", equipment=["pie plate"])
    assert await now() == (recorded + 2, recipes + 3)
    approved = await mo.post(f"/api/review/recipes/{waiting}", json={"action": "approve"})
    assert approved.status_code == 200, approved.text
    assert await now() == (recorded + 3, recipes + 4)
    # Nor is one in a family's collection, the moderator's own included:
    # the numbers are the same whoever asks.
    for whose in (await people("fay"), mo):
        box = (
            await whose.post("/api/sources/family", json={"title": "Box", "acknowledged": True})
        ).json()["id"]
        await _recipe(whose, box, None, "Nana's", equipment=["wok"])
    assert await now() == (recorded + 3, recipes + 4)
    # A recipe deleted leaves with what it had recorded.
    assert (await mo.delete(f"/api/recipes/{plain}")).status_code == 204
    assert await now() == (recorded + 3, recipes + 3)
