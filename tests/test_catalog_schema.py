"""The catalog rules the database enforces, exercised against the migration."""

import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from openlarder.models import Base


def _diet(db: Connection, name: str) -> uuid.UUID:
    """One of the diets migration 0018 seeds."""
    return db.scalar(text("SELECT id FROM tags WHERE kind = 'diet' AND name = :n"), {"n": name})


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


def _line(db: Connection, recipe_id, position: int, original_text: str) -> uuid.UUID:
    return _insert(
        db,
        "INSERT INTO recipe_ingredients (recipe_id, position, original_text) VALUES (:r, :p, :t)",
        r=recipe_id,
        p=position,
        t=original_text,
    )


def _option(
    db: Connection, line_id, recipe_id, rank: int, name: str, ingredient=None, sub_recipe=None
) -> uuid.UUID:
    return _insert(
        db,
        "INSERT INTO ingredient_options"
        " (recipe_ingredient_id, recipe_id, rank, name, ingredient_id, sub_recipe_id)"
        " VALUES (:l, :r, :k, :n, :i, :s)",
        l=line_id,
        r=recipe_id,
        k=rank,
        n=name,
        i=ingredient,
        s=sub_recipe,
    )


def test_option_has_at_most_one_target(db: Connection) -> None:
    work = _work(db)
    recipe, blend = _recipe(db, work), _recipe(db, work, "Flour Blend")
    flour = _insert(
        db, "INSERT INTO ingredients (name, match_key) VALUES ('rice flour', 'rice flour')"
    )
    line = _line(db, recipe, 1, "2 cups flour")
    _option(db, line, recipe, 1, "flour")  # not matched yet
    _option(db, line, recipe, 2, "rice flour", ingredient=flour)
    _option(db, line, recipe, 3, "Flour Blend", sub_recipe=blend)
    _refused(db, lambda: _option(db, line, recipe, 4, "x", ingredient=flour, sub_recipe=blend))


def test_line_ranks_a_first_choice_and_fallbacks(db: Connection) -> None:
    work = _work(db)
    recipe = _recipe(db, work, "Cottage Cheese Pancakes")
    grapeseed = _insert(
        db, "INSERT INTO ingredients (name, match_key) VALUES ('grapeseed oil', 'grapeseed oil')"
    )
    olive = _insert(
        db, "INSERT INTO ingredients (name, match_key) VALUES ('olive oil', 'olive oil')"
    )
    line = _line(db, recipe, 1, "Grapeseed Oil or Olive Oil")
    _option(db, line, recipe, 2, "Olive Oil", ingredient=olive)
    _option(db, line, recipe, 1, "Grapeseed Oil", ingredient=grapeseed)
    ranked = db.execute(
        text(
            "SELECT ingredient_id FROM ingredient_options WHERE recipe_ingredient_id = :l"
            " ORDER BY rank"
        ),
        {"l": line},
    ).scalars()
    assert list(ranked) == [grapeseed, olive]
    _refused(db, lambda: _option(db, line, recipe, 2, "Canola Oil"))
    _refused(db, lambda: _option(db, line, recipe, 0, "Canola Oil"))


def test_option_cannot_list_its_own_recipe_or_claim_another_recipes_line(
    db: Connection,
) -> None:
    work = _work(db)
    recipe, other = _recipe(db, work), _recipe(db, work, "Focaccia")
    line = _line(db, recipe, 1, "1 batch dressing")
    _refused(db, lambda: _option(db, line, recipe, 1, "dressing", sub_recipe=recipe))
    # The line belongs to recipe; an option saying it belongs to other is refused.
    _refused(db, lambda: _option(db, line, other, 1, "dressing"))


def test_ingredient_names_are_unique_ignoring_case(db: Connection) -> None:
    _insert(db, "INSERT INTO ingredients (name, match_key) VALUES ('Green Onion', 'Green Onion')")
    _refused(
        db,
        lambda: _insert(
            db, "INSERT INTO ingredients (name, match_key) VALUES ('green onion', 'other key')"
        ),
    )


def test_alias_unique_per_region_including_unmarked(db: Connection) -> None:
    onion = _insert(
        db, "INSERT INTO ingredients (name, match_key) VALUES ('green onion', 'green onion')"
    )
    alias = (
        "INSERT INTO ingredient_aliases (ingredient_id, name, match_key, region)"
        " VALUES (:i, :n, :k, :r)"
    )
    _insert(db, alias, i=onion, n="scallion", k="scallion", r=None)
    _insert(db, alias, i=onion, n="spring onion", k="spring onion", r="UK")
    _insert(db, alias, i=onion, n="spring onion", k="spring onion", r="AU")
    _refused(db, lambda: _insert(db, alias, i=onion, n="Scallion", k="other", r=None))
    _refused(db, lambda: _insert(db, alias, i=onion, n="spring onion", k="x", r="UK"))
    _refused(db, lambda: _insert(db, alias, i=onion, n="shallot", k="shallot", r="FR"))


def test_one_unmarked_alias_per_match_key(db: Connection) -> None:
    onion = _insert(
        db, "INSERT INTO ingredients (name, match_key) VALUES ('green onion', 'green onion')"
    )
    alias = (
        "INSERT INTO ingredient_aliases (ingredient_id, name, match_key, region)"
        " VALUES (:i, :n, :k, :r)"
    )
    _insert(db, alias, i=onion, n="scallions", k="scallion", r=None)
    _insert(db, alias, i=onion, n="scallion (UK)", k="scallion", r="UK")
    _refused(db, lambda: _insert(db, alias, i=onion, n="Scallion!", k="scallion", r=None))
    _refused(db, lambda: _insert(db, alias, i=onion, n="nothing", k="", r=None))


def test_ingredient_in_use_cannot_be_deleted(db: Connection) -> None:
    work = _work(db)
    recipe = _recipe(db, work)
    egg = _insert(db, "INSERT INTO ingredients (name, match_key) VALUES ('egg', 'egg')")
    _option(db, _line(db, recipe, 1, "1 egg"), recipe, 1, "egg", ingredient=egg)
    _refused(db, lambda: db.execute(text("DELETE FROM ingredients WHERE id = :i"), {"i": egg}))


def test_recipes_inherit_their_books_tags_once(db: Connection) -> None:
    work = _work(db)
    recipe = _recipe(db, work)
    gf = _diet(db, "Gluten-Free")
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


def test_existing_lines_keep_their_targets_and_downgrade_keeps_fallbacks(
    engine, alembic_config
) -> None:
    """Data written under 0001 survives 0002; 0002 will not go back and drop a fallback."""
    engine.dispose()
    command.downgrade(alembic_config, "0001")
    try:
        with engine.begin() as conn:
            work = _work(conn, "Migration Test")
            recipe, blend = _recipe(conn, work), _recipe(conn, work, "Biscuit Blend")
            egg = _insert(conn, "INSERT INTO ingredients (name) VALUES ('migration egg')")
            old_line = (
                "INSERT INTO recipe_ingredients"
                " (recipe_id, position, original_text, ingredient_id, sub_recipe_id)"
                " VALUES (:r, :p, :t, :i, :s)"
            )
            for p, t, i, s in [
                (1, "Egg", egg, None),
                (2, "Biscuit Blend (p. 14)", None, blend),
                (3, "Salt", None, None),
            ]:
                conn.execute(text(old_line), {"r": recipe, "p": p, "t": t, "i": i, "s": s})

        engine.dispose()
        command.upgrade(alembic_config, "head")
        with engine.begin() as conn:
            options = conn.execute(
                text(
                    "SELECT ri.position, o.rank, o.name, o.ingredient_id, o.sub_recipe_id"
                    " FROM ingredient_options o"
                    " JOIN recipe_ingredients ri ON ri.id = o.recipe_ingredient_id"
                    " WHERE ri.recipe_id = :r ORDER BY ri.position"
                ),
                {"r": recipe},
            ).all()
            assert [tuple(o) for o in options] == [
                (1, 1, "Egg", egg, None),
                (2, 1, "Biscuit Blend (p. 14)", None, blend),
                (3, 1, "Salt", None, None),
            ]
            line = conn.execute(
                text("SELECT id FROM recipe_ingredients WHERE recipe_id = :r AND position = 3"),
                {"r": recipe},
            ).scalar_one()
            _option(conn, line, recipe, 2, "Sea Salt")

        engine.dispose()
        with pytest.raises(RuntimeError, match="fallback"):
            command.downgrade(alembic_config, "0001")
    finally:
        engine.dispose()
        command.upgrade(alembic_config, "head")
        with engine.begin() as conn:
            # Options first: RESTRICT refuses to delete a recipe still used as
            # a sub-recipe, even by a row the same cascade would remove.
            conn.execute(
                text(
                    "DELETE FROM ingredient_options WHERE recipe_id IN (SELECT r.id FROM recipes r"
                    " JOIN works w ON w.id = r.work_id WHERE w.title = 'Migration Test')"
                )
            )
            conn.execute(text("DELETE FROM works WHERE title = 'Migration Test'"))
            conn.execute(text("DELETE FROM ingredients WHERE name = 'migration egg'"))


def _author(db: Connection, name: str, kind: str = "person", wikidata_id=None) -> uuid.UUID:
    return _insert(
        db,
        "INSERT INTO authors (name, kind, wikidata_id) VALUES (:n, :k, :q)",
        n=name,
        k=kind,
        q=wikidata_id,
    )


def _credit(db: Connection, work_id, author_id, position: int, credited_as: str, role="author"):
    return _insert(
        db,
        "INSERT INTO work_credits (work_id, author_id, position, role, credited_as)"
        " VALUES (:w, :a, :p, :r, :c)",
        w=work_id,
        a=author_id,
        p=position,
        r=role,
        c=credited_as,
    )


def test_credits_keep_printed_order_and_name(db: Connection) -> None:
    paleo, approach = _work(db, "Paleo Principles"), _work(db, "The Paleo Approach Cookbook")
    sarah = _author(db, "Sarah Ballantyne")
    atk = _author(db, "America's Test Kitchen", kind="organisation")
    _credit(db, paleo, atk, 2, "America's Test Kitchen", role="contributor")
    _credit(db, paleo, sarah, 1, "Sarah Ballantyne, PhD")
    _credit(db, approach, sarah, 1, "Sarah Ballantyne, PhD")
    credits = db.execute(
        text(
            "SELECT author_id, credited_as FROM work_credits WHERE work_id = :w ORDER BY position"
        ),
        {"w": paleo},
    ).all()
    assert [tuple(c) for c in credits] == [
        (sarah, "Sarah Ballantyne, PhD"),
        (atk, "America's Test Kitchen"),
    ]
    books = db.execute(
        text("SELECT count(*) FROM work_credits WHERE author_id = :a"), {"a": sarah}
    ).scalar_one()
    assert books == 2


def test_credit_rules(db: Connection) -> None:
    work = _work(db, "Franklin Barbecue")
    aaron = _author(db, "Aaron Franklin")
    _credit(db, work, aaron, 1, "Aaron Franklin")
    _credit(db, work, aaron, 2, "Aaron Franklin", role="photographer")  # another role: allowed
    jordan = _author(db, "Jordan Mackay")
    _refused(db, lambda: _credit(db, work, jordan, 1, "Jordan Mackay"))  # position taken
    _refused(db, lambda: _credit(db, work, aaron, 3, "Aaron Franklin"))  # same role again
    _refused(db, lambda: _credit(db, work, jordan, 3, "Jordan Mackay", role="ghost"))
    _refused(db, lambda: _credit(db, work, jordan, 3, ""))


def test_author_still_credited_cannot_be_deleted(db: Connection) -> None:
    work = _work(db, "Plenty")
    yotam = _author(db, "Yotam Ottolenghi")
    _credit(db, work, yotam, 1, "Yotam Ottolenghi")
    delete = text("DELETE FROM authors WHERE id = :a")
    _refused(db, lambda: db.execute(delete, {"a": yotam}))
    # Deleting the book takes its credits with it, and frees the author.
    db.execute(text("DELETE FROM works WHERE id = :w"), {"w": work})
    db.execute(delete, {"a": yotam})


def test_author_kind_and_wikidata_id(db: Connection) -> None:
    _author(db, "The Culinary Institute of America", kind="organisation", wikidata_id="Q1144556")
    _refused(db, lambda: _author(db, "Someone", kind="pseudonym"))
    _refused(db, lambda: _author(db, "Someone", wikidata_id="1144556"))


def test_author_lists_become_credits_and_downgrade_keeps_roles(engine, alembic_config) -> None:
    """Names listed on works under 0002 become authors and credits under 0003."""
    engine.dispose()
    command.downgrade(alembic_config, "0002")
    titles = ("Credit Test A", "Credit Test B")
    try:
        with engine.begin() as conn:
            listed = "INSERT INTO works (title, authors) VALUES (:t, :a) RETURNING id"
            a = conn.execute(
                text(listed),
                {"t": titles[0], "a": ["Michelle Tam", "Henry Fong", "Michelle Tam", ""]},
            ).scalar_one()
            b = conn.execute(text(listed), {"t": titles[1], "a": ["Michelle Tam"]}).scalar_one()

        engine.dispose()
        command.upgrade(alembic_config, "head")
        with engine.begin() as conn:

            def credits(work):
                rows = conn.execute(
                    text(
                        "SELECT c.position, c.role, c.credited_as, a.name FROM work_credits c"
                        " JOIN authors a ON a.id = c.author_id WHERE c.work_id = :w"
                        " ORDER BY c.position"
                    ),
                    {"w": work},
                ).all()
                return [tuple(r) for r in rows]

            # The repeat of Michelle Tam and the empty name are dropped.
            assert credits(a) == [
                (1, "author", "Michelle Tam", "Michelle Tam"),
                (2, "author", "Henry Fong", "Henry Fong"),
            ]
            assert credits(b) == [(1, "author", "Michelle Tam", "Michelle Tam")]
            shared = conn.execute(
                text("SELECT count(*) FROM authors WHERE name = 'Michelle Tam'")
            ).scalar_one()
            assert shared == 1

            henry = conn.execute(text("SELECT id FROM authors WHERE name = 'Henry Fong'"))
            _credit(conn, b, henry.scalar_one(), 2, "Henry Fong", role="photographer")

        engine.dispose()
        with pytest.raises(RuntimeError, match="role"):
            command.downgrade(alembic_config, "0002")
    finally:
        engine.dispose()
        command.upgrade(alembic_config, "head")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM works WHERE title = ANY(:t)"), {"t": list(titles)})
            conn.execute(text("DELETE FROM authors WHERE name IN ('Michelle Tam', 'Henry Fong')"))


def _swap(db: Connection, **cols) -> uuid.UUID:
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return _insert(db, f"INSERT INTO substitutions ({names}) VALUES ({values})", **cols)


def _ingredient(db: Connection, name: str) -> uuid.UUID:
    return _insert(db, "INSERT INTO ingredients (name, match_key) VALUES (:n, :n)", n=name)


def test_substitution_from_a_book_and_between_blends(db: Connection) -> None:
    book = _work(db, "The How Can It Be Gluten Free Cookbook Vol. 2")
    edition = _edition(db, book)
    butter, vegan = _ingredient(db, "butter"), _ingredient(db, "vegan butter")
    dairy_free = _diet(db, "Dairy-Free")
    _swap(
        db,
        from_ingredient_id=butter,
        to_ingredient_id=vegan,
        diet_tag_id=dairy_free,
        source_edition_id=edition,
        source_page="54",
    )
    # The same swap printed in another book's edition is a second source, not a duplicate.
    other = _edition(db, _work(db, "Another Book"))
    _swap(
        db,
        from_ingredient_id=butter,
        to_ingredient_id=vegan,
        diet_tag_id=dairy_free,
        source_edition_id=other,
    )
    _refused(
        db,
        lambda: _swap(
            db,
            from_ingredient_id=butter,
            to_ingredient_id=vegan,
            diet_tag_id=dairy_free,
            source_edition_id=other,
        ),
    )
    # One book's blend for another's, contributed, for no particular diet; twice is a duplicate.
    atk = _recipe(db, book, "All-Purpose Flour Blend")
    morgan = _recipe(db, _work(db, "The Everyday Art of Gluten-Free"), "Cake & Muffin Blend")
    _swap(db, from_recipe_id=atk, to_recipe_id=morgan)
    _refused(db, lambda: _swap(db, from_recipe_id=atk, to_recipe_id=morgan))
    # The reverse direction is its own row.
    _swap(db, from_recipe_id=morgan, to_recipe_id=atk)


def test_substitution_has_one_thing_on_each_side_and_never_itself(db: Connection) -> None:
    work = _work(db)
    egg, flax = _ingredient(db, "egg"), _ingredient(db, "flax egg")
    blend = _recipe(db, work, "Flour Blend")
    _swap(db, from_ingredient_id=egg, to_recipe_id=blend)  # mixed sides are fine
    _refused(db, lambda: _swap(db, to_ingredient_id=flax))
    _refused(db, lambda: _swap(db, from_ingredient_id=egg))
    _refused(
        db, lambda: _swap(db, from_ingredient_id=egg, from_recipe_id=blend, to_ingredient_id=flax)
    )
    _refused(db, lambda: _swap(db, from_ingredient_id=egg, to_ingredient_id=egg))
    _refused(db, lambda: _swap(db, from_recipe_id=blend, to_recipe_id=blend))


def test_substitution_reason_is_a_diet_and_page_needs_an_edition(db: Connection) -> None:
    butter, ghee = _ingredient(db, "butter"), _ingredient(db, "ghee")
    salad = _insert(db, "INSERT INTO tags (kind, name) VALUES ('course', 'Salad')")
    _refused(
        db, lambda: _swap(db, from_ingredient_id=butter, to_ingredient_id=ghee, diet_tag_id=salad)
    )
    _refused(
        db,
        lambda: _swap(
            db,
            from_ingredient_id=butter,
            to_ingredient_id=ghee,
            diet_kind="course",
            diet_tag_id=salad,
        ),
    )
    _refused(
        db, lambda: _swap(db, from_ingredient_id=butter, to_ingredient_id=ghee, source_page="12")
    )
    edition = _edition(db, _work(db))
    _refused(
        db,
        lambda: _swap(
            db,
            from_ingredient_id=butter,
            to_ingredient_id=ghee,
            source_edition_id=edition,
            source_page="",
        ),
    )


def test_substitution_amount_is_an_optional_note(db: Connection) -> None:
    egg, aquafaba = _ingredient(db, "egg"), _ingredient(db, "aquafaba")
    _swap(db, from_ingredient_id=egg, to_ingredient_id=aquafaba, note="3 tablespoons per egg")
    _refused(db, lambda: _swap(db, from_ingredient_id=aquafaba, to_ingredient_id=egg, note=""))


def test_substitution_goes_with_its_recipe_but_holds_its_ingredient(db: Connection) -> None:
    work = _work(db)
    blend = _recipe(db, work, "Flour Blend")
    flour = _ingredient(db, "rice flour")
    swap = _swap(db, from_ingredient_id=flour, to_recipe_id=blend)
    _refused(db, lambda: db.execute(text("DELETE FROM ingredients WHERE id = :i"), {"i": flour}))
    db.execute(text("DELETE FROM recipes WHERE id = :r"), {"r": blend})
    left = db.execute(text("SELECT count(*) FROM substitutions WHERE id = :s"), {"s": swap})
    assert left.scalar_one() == 0


def test_downgrade_keeps_substitutions(engine, alembic_config) -> None:
    with engine.begin() as conn:
        a, b = _ingredient(conn, "downgrade butter"), _ingredient(conn, "downgrade ghee")
        _swap(conn, from_ingredient_id=a, to_ingredient_id=b)
    try:
        engine.dispose()
        with pytest.raises(RuntimeError, match="substitution"):
            command.downgrade(alembic_config, "0003")
    finally:
        engine.dispose()
        command.upgrade(alembic_config, "head")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM substitutions WHERE from_ingredient_id = :a"), {"a": a})
            conn.execute(text("DELETE FROM ingredients WHERE id IN (:a, :b)"), {"a": a, "b": b})
