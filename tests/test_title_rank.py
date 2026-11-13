"""Which of the recipes a title search finds come first (title_rank.py)."""

import pytest
from sqlalchemy import text

from openlarder import title_rank


@pytest.fixture
async def book(people, adb):
    """Adds recipes to one book: add(title, ingredients, spoons) gives the
    recipe's id, rated by as many people as there are spoons given."""
    mo = await people("mo", role="moderator")
    made = await mo.post("/api/sources/manual", json={"title": "Plenty", "authors": ["Ann Author"]})
    source = made.json()["id"]
    edition = str(
        await adb.scalar(text("SELECT id FROM editions WHERE source_id = :s"), {"s": source})
    )
    raters = []
    pages = iter(range(1, 1000))

    async def add(title, ingredients=("Flour",), spoons=()):
        made = await mo.post(
            f"/api/sources/{source}/recipes",
            json={
                "title": title,
                "editions": [{"edition_id": edition, "page": str(next(pages))}],
                "ingredients": list(ingredients),
            },
        )
        assert made.status_code == 201, made.text
        while len(raters) < len(spoons):
            raters.append(await people(f"rater{len(raters)}"))
        for rater, given in zip(raters, spoons, strict=False):
            rated = await rater.put(
                f"/api/recipes/{made.json()['id']}/rating", json={"spoons": given}
            )
            assert rated.status_code == 200, rated.text
        return made.json()["id"]

    return add


def test_no_words_no_order() -> None:
    assert title_rank.order([], "") == []


async def _found(client, **params):
    response = await client.get("/api/search", params=params)
    assert response.status_code == 200, response.text
    return [r["title"] for r in response.json()["recipes"]]


async def test_whole_words_then_a_words_beginning_then_inside_one(book, client) -> None:
    # Added in an order that is none of the ones below, A to Z included.
    for title in (
        "Pancakes",
        "Cakewalk Cookies",
        "Banana Mouse Pancakes",
        "Carrot Cake",
        "Cheesecake",
        "Crab Cakes",
    ):
        await book(title)
    await book("Toast")
    assert await _found(client, q="cake") == [
        # A whole word of the title, and a plural is: the shorter first.
        "Crab Cakes",
        "Carrot Cake",
        # Begins a word.
        "Cakewalk Cookies",
        # Inside one: still found.
        "Pancakes",
        "Cheesecake",
        "Banana Mouse Pancakes",
    ]


async def test_the_title_typed_comes_first_of_all(book, client) -> None:
    for title in ("Rye", "Rye Bread", "A Rye Bread"):
        await book(title)
    await book("Rye Bread Pudding", spoons=[5])
    # However it was typed, case and spacing aside. Before a rated recipe
    # whose title is as close, which comes before a shorter one.
    for typed in ("rye bread", "  RYE   Bread "):
        assert await _found(client, q=typed) == ["Rye Bread", "Rye Bread Pudding", "A Rye Bread"]


async def test_rated_recipes_come_first_among_titles_as_close(book, client) -> None:
    await book("Leek Soup")
    await book("A Hearty Winter Barley Soup", spoons=[4])
    await book("Carrot and Coriander Soup", spoons=[5, 5])
    await book("Dill Soup", spoons=[5])
    await book("Soupy Rice", spoons=[5, 5, 5])
    assert await _found(client, q="soup") == [
        # Whole word: the higher average, then the more who rated it, then
        # the unrated; a rating counts before a shorter title.
        "Carrot and Coriander Soup",
        "Dill Soup",
        "A Hearty Winter Barley Soup",
        "Leek Soup",
        # Three people's five spoons, but a title less close.
        "Soupy Rice",
    ]
    # Asked for the highest rated, the rating comes before the title.
    assert await _found(client, q="soup", sort="rating") == [
        "Soupy Rice",
        "Carrot and Coriander Soup",
        "Dill Soup",
        "A Hearty Winter Barley Soup",
        "Leek Soup",
    ]


async def test_titles_as_close_and_as_long_are_a_to_z(book, client) -> None:
    for title in ("Lemon Cake", "Honey Cake", "honey Bake", "Apple Cake"):
        await book(title)
    assert await _found(client, q="cake") == ["Apple Cake", "Honey Cake", "Lemon Cake"]
    assert await _found(client, q="honey") == ["honey Bake", "Honey Cake"]


async def test_every_word_has_to_be_as_close(book, client) -> None:
    titles = ("Carrot Pancake", "Carrot Cakewalk", "Spiced Carrot Cake", "Carrots in Pancakes")
    for title in titles:
        await book(title)
    assert await _found(client, q="carrot cake") == [
        "Spiced Carrot Cake",
        # Both begin a word.
        "Carrot Cakewalk",
        # "Carrot" is a whole word and "cake" inside one: that's no closer
        # than both inside, though the title is shorter than the one above.
        "Carrot Pancake",
        "Carrots in Pancakes",
    ]


async def test_what_you_have_still_ranks_first(book, client, adb) -> None:
    await book("Apple Pancakes", ["Rhubarb", "Flour"])
    await book("Rhubarb Cake", ["Rhubarb", "Butter"])
    await book("Zebra Cheesecake", ["Rhubarb", "Ginger"])
    await book("Rhubarb Fool", ["Rhubarb", "Ginger"])

    async def named(name):
        found = await adb.scalar(text("SELECT id FROM ingredients WHERE name = :n"), {"n": name})
        return str(found)

    rhubarb, ginger = await named("Rhubarb"), await named("Ginger")
    assert await _found(client, q="cake", ingredient=[rhubarb, ginger]) == [
        # Uses both of yours, though "cake" is only inside its title.
        "Zebra Cheesecake",
        # Level on what you have: the closer title, not A to Z.
        "Rhubarb Cake",
        "Apple Pancakes",
    ]


async def test_without_title_words_the_order_is_by_book(book, client, adb) -> None:
    await book("Zucchini Slice", ["Rhubarb"], spoons=[5])
    await book("Apple Slice", ["Rhubarb"])
    rhubarb = str(await adb.scalar(text("SELECT id FROM ingredients WHERE name = 'Rhubarb'")))
    assert await _found(client, ingredient=[rhubarb]) == ["Apple Slice", "Zucchini Slice"]


@pytest.mark.parametrize(
    "typed, first",
    [
        # What someone typed is never a pattern.
        ("c++", "C++ Cake"),
        ("(", "Rice (Plain)"),
        ("50%", "50% Rye Loaf"),
        ("a.b", "A.B. Sauce"),
        ("[", "Soup [Winter]"),
        ("\\", "Either\\Or Pie"),
        ("*", "Five* Spice"),
        ("^", "Hat ^ Trick"),
        # Words the English reading drops: found, with none in the first group.
        ("the", "The Brownies"),
        ("and the", "Salt and the Sea"),
    ],
)
async def test_whatever_is_typed_is_searched_for_as_typed(book, client, typed, first) -> None:
    for title in (
        "C++ Cake",
        "Rice (Plain)",
        "50% Rye Loaf",
        "A.B. Sauce",
        "Soup [Winter]",
        "Either\\Or Pie",
        "Five* Spice",
        "Hat ^ Trick",
        "The Brownies",
        "Salt and the Sea",
    ):
        await book(title)
    assert (await _found(client, q=typed))[0] == first
