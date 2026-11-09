"""Suggestions, embeddings, and what n8n's role may read and write (0029)."""

import json
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

ROLE_SQL = Path(__file__).resolve().parents[1] / "scripts" / "n8n_role.sql"


async def _ingredient(adb, name):
    return await adb.scalar(
        text("INSERT INTO ingredients (name, match_key) VALUES (:n, :n) RETURNING id"), {"n": name}
    )


def _vector(*leading: float) -> str:
    values = list(leading) + [0.0] * (768 - len(leading))
    return "[" + ",".join(str(v) for v in values) + "]"


async def test_the_nearest_ingredient_is_found_by_its_embedding(adb) -> None:
    onion, scallion, cocoa = [
        await _ingredient(adb, n) for n in ("green onion", "scallion", "cocoa")
    ]
    for ingredient, vector in (
        (onion, _vector(1, 0.1)),
        (scallion, _vector(1, 0.2)),
        (cocoa, _vector(0, 1)),
    ):
        await adb.execute(
            text(
                "INSERT INTO ingredient_embeddings (ingredient_id, model, text_embedded, embedding)"
                " VALUES (:i, 'embeddinggemma', 'x', CAST(:v AS vector))"
            ),
            {"i": ingredient, "v": vector},
        )
    nearest = await adb.scalar(
        text(
            "SELECT b.ingredient_id FROM ingredient_embeddings a, ingredient_embeddings b"
            " WHERE a.ingredient_id = :o AND b.ingredient_id <> a.ingredient_id"
            " ORDER BY a.embedding <=> b.embedding LIMIT 1"
        ),
        {"o": onion},
    )
    assert nearest == scallion


async def test_a_rerun_adds_no_second_open_suggestion(adb) -> None:
    insert = text(
        "INSERT INTO suggestions (kind, target, proposal, model, prompt_version)"
        " VALUES ('merge', CAST(:t AS jsonb), '{}', 'gemma4:12b', 'merge-v1')"
        " ON CONFLICT DO NOTHING RETURNING id"
    )
    target = json.dumps([str(uuid.uuid4()), str(uuid.uuid4())])
    first = await adb.scalar(insert, {"t": target})
    assert first is not None
    assert await adb.scalar(insert, {"t": target}) is None
    # Once decided, it no longer blocks; the workflow's own NOT EXISTS is
    # what keeps a dismissed pair from coming back.
    await adb.execute(
        text("UPDATE suggestions SET status = 'dismissed', decided_at = now() WHERE id = :i"),
        {"i": first},
    )
    assert await adb.scalar(insert, {"t": target}) is not None


async def test_a_decided_suggestion_says_when(adb) -> None:
    with pytest.raises(IntegrityError):
        async with adb.begin_nested():
            await adb.execute(
                text(
                    "INSERT INTO suggestions"
                    " (kind, target, proposal, model, prompt_version, status)"
                    " VALUES ('merge', '[]', '{}', 'm', 'v', 'accepted')"
                )
            )


# The role, made by the script itself.


@pytest.fixture
async def n8n(adb):
    """The script's role under a throwaway name, and a way to act as it."""
    role = f"n8n_test_{uuid.uuid4().hex[:8]}"
    database = await adb.scalar(text("SELECT current_database()"))
    script = (
        ROLE_SQL.read_text(encoding="utf-8")
        .replace(':"role"', f'"{role}"')
        .replace(':"DBNAME"', f'"{database}"')
        .replace(":'password'", "'not-a-real-password'")
    )
    script = re.sub(r"--[^\n]*", "", script)
    for statement in filter(str.strip, script.split(";")):
        await adb.execute(text(statement))

    async def as_role(sql, **params):
        # SET LOCAL would outlast the savepoint; the role goes with the
        # test's rollback, so nothing is dropped after.
        await adb.execute(text(f'SET ROLE "{role}"'))
        try:
            async with adb.begin_nested():
                return await adb.execute(text(sql), params)
        finally:
            await adb.execute(text("RESET ROLE"))

    return as_role


async def test_the_role_reads_the_views_and_not_the_tables(n8n, adb) -> None:
    await _ingredient(adb, "rhubarb")
    assert [r.name for r in await n8n("SELECT name FROM public_ingredients")] == ["rhubarb"]
    for table in ("ingredients", "recipe_ingredients", "sources", "users"):
        with pytest.raises(DBAPIError, match="permission denied"):
            await n8n(f"SELECT 1 FROM {table}")


async def test_the_role_writes_embeddings_and_adds_suggestions(n8n, adb) -> None:
    rhubarb = await _ingredient(adb, "rhubarb")
    await n8n(
        "INSERT INTO ingredient_embeddings (ingredient_id, model, text_embedded, embedding)"
        " VALUES (:i, 'embeddinggemma', 'rhubarb', CAST(:v AS vector))",
        i=rhubarb,
        v=_vector(1),
    )
    added = await n8n(
        "INSERT INTO suggestions (kind, target, proposal, model, prompt_version)"
        " VALUES ('merge', '[1, 2]', '{}', 'gemma4:12b', 'merge-v1') RETURNING id"
    )
    suggestion = added.scalar()
    # Deciding is the site's.
    for sql in (
        "UPDATE suggestions SET status = 'accepted', decided_at = now()",
        "DELETE FROM suggestions",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            await n8n(sql)
    assert suggestion is not None
