"""The catalog rules the database enforces, exercised against the migration."""

import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from openlarder.models import Base


def _insert(db: Connection, sql: str, **params) -> uuid.UUID:
    return db.execute(text(sql + " RETURNING id"), params).scalar_one()


def _work(db: Connection, title: str = "Salt Fat Acid Heat") -> uuid.UUID:
    return _insert(db, "INSERT INTO works (title) VALUES (:t)", t=title)


def _edition(db: Connection, work_id: uuid.UUID, isbn13: str | None = None) -> uuid.UUID:
    return _insert(
        db, "INSERT INTO editions (work_id, isbn13) VALUES (:w, :i)", w=work_id, i=isbn13
    )


def _recipe(db: Connection, work_id: uuid.UUID, title: str = "Caesar Salad") -> uuid.UUID:
    return _insert(db, "INSERT INTO recipes (work_id, title) VALUES (:w, :t)", w=work_id, t=title)


def _page(db: Connection, recipe_id, edition_id, work_id, page: str | None) -> None:
    db.execute(
        text(
            "INSERT INTO recipe_pages (recipe_id, edition_id, work_id, page)"
            " VALUES (:r, :e, :w, :p)"
        ),
        {"r": recipe_id, "e": edition_id, "w": work_id, "p": page},
    )


def _refused(db: Connection, fn) -> None:
    """Run fn inside a savepoint and assert the database refused it."""
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            fn()


def test_models_match_the_migration(engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_downgrade_and_upgrade_round_trip(engine, alembic_config) -> None:
    engine.dispose()
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_page_is_optional_but_not_blank(db: Connection) -> None:
    work = _work(db)
    edition = _edition(db, work)
    recipe = _recipe(db, work)
    _page(db, recipe, edition, work, None)
    other = _recipe(db, work, "Focaccia")
    _refused(db, lambda: _page(db, other, edition, work, ""))


def test_page_cannot_join_a_recipe_to_another_books_edition(db: Connection) -> None:
    book_a, book_b = _work(db, "A"), _work(db, "B")
    recipe = _recipe(db, book_a)
    foreign_edition = _edition(db, book_b)
    # Claiming either work is refused: one side of the pair never matches.
    _refused(db, lambda: _page(db, recipe, foreign_edition, book_a, "12"))
    _refused(db, lambda: _page(db, recipe, foreign_edition, book_b, "12"))


def test_isbn13_format(db: Connection) -> None:
    work = _work(db)
    _edition(db, work, "9780393541113")
    _refused(db, lambda: _edition(db, work, "0393541118"))


def test_recipe_ingredient_has_at_most_one_target(db: Connection) -> None:
    work = _work(db)
    recipe, blend = _recipe(db, work), _recipe(db, work, "Flour Blend")
    flour = _insert(db, "INSERT INTO ingredients (name) VALUES ('rice flour')")
    line = (
        "INSERT INTO recipe_ingredients"
        " (recipe_id, position, original_text, ingredient_id, sub_recipe_id)"
        " VALUES (:r, :p, '2 cups flour', :i, :s)"
    )
    db.execute(text(line), {"r": recipe, "p": 1, "i": None, "s": None})  # not matched yet
    db.execute(text(line), {"r": recipe, "p": 2, "i": flour, "s": None})
    db.execute(text(line), {"r": recipe, "p": 3, "i": None, "s": blend})
    _refused(db, lambda: db.execute(text(line), {"r": recipe, "p": 4, "i": flour, "s": blend}))
    _refused(db, lambda: db.execute(text(line), {"r": recipe, "p": 5, "i": None, "s": recipe}))


def test_ingredient_names_are_unique_ignoring_case(db: Connection) -> None:
    _insert(db, "INSERT INTO ingredients (name) VALUES ('Green Onion')")
    _refused(db, lambda: _insert(db, "INSERT INTO ingredients (name) VALUES ('green onion')"))


def test_alias_unique_per_region_including_unmarked(db: Connection) -> None:
    onion = _insert(db, "INSERT INTO ingredients (name) VALUES ('green onion')")
    alias = "INSERT INTO ingredient_aliases (ingredient_id, name, region) VALUES (:i, :n, :r)"
    _insert(db, alias, i=onion, n="scallion", r=None)
    _insert(db, alias, i=onion, n="spring onion", r="UK")
    _insert(db, alias, i=onion, n="spring onion", r="AU")
    _refused(db, lambda: _insert(db, alias, i=onion, n="Scallion", r=None))
    _refused(db, lambda: _insert(db, alias, i=onion, n="spring onion", r="UK"))
    _refused(db, lambda: _insert(db, alias, i=onion, n="shallot", r="FR"))


def test_ingredient_in_use_cannot_be_deleted(db: Connection) -> None:
    work = _work(db)
    recipe = _recipe(db, work)
    egg = _insert(db, "INSERT INTO ingredients (name) VALUES ('egg')")
    db.execute(
        text(
            "INSERT INTO recipe_ingredients (recipe_id, position, original_text, ingredient_id)"
            " VALUES (:r, 1, '1 egg', :i)"
        ),
        {"r": recipe, "i": egg},
    )
    _refused(db, lambda: db.execute(text("DELETE FROM ingredients WHERE id = :i"), {"i": egg}))


def test_recipes_inherit_their_books_tags_once(db: Connection) -> None:
    work = _work(db)
    recipe = _recipe(db, work)
    gf = _insert(db, "INSERT INTO tags (kind, name) VALUES ('diet', 'Gluten-Free')")
    salad = _insert(db, "INSERT INTO tags (kind, name) VALUES ('course', 'Salad')")
    db.execute(text("INSERT INTO work_tags VALUES (:w, :t)"), {"w": work, "t": gf})
    db.execute(text("INSERT INTO recipe_tags VALUES (:r, :t)"), {"r": recipe, "t": salad})

    def effective() -> set[tuple[uuid.UUID, bool]]:
        rows = db.execute(
            text("SELECT tag_id, inherited FROM recipe_effective_tags WHERE recipe_id = :r"),
            {"r": recipe},
        )
        return {tuple(row) for row in rows}

    assert effective() == {(gf, True), (salad, False)}

    # Set on the recipe too: listed once, as its own.
    db.execute(text("INSERT INTO recipe_tags VALUES (:r, :t)"), {"r": recipe, "t": gf})
    assert effective() == {(gf, False), (salad, False)}


def test_updated_at_moves_on_update(db: Connection) -> None:
    work = _work(db)
    # now() is fixed within a transaction, so backdate rather than wait.
    db.execute(
        text("UPDATE works SET updated_at = now() - interval '1 day' WHERE id = :w"), {"w": work}
    )
    db.execute(text("UPDATE works SET subtitle = 'x' WHERE id = :w"), {"w": work})
    moved = db.execute(
        text("SELECT updated_at = now() FROM works WHERE id = :w"), {"w": work}
    ).scalar_one()
    assert moved
