"""The database's CHECK constraints are the ones the models describe, by name.

alembic check compares tables, columns, keys and indexes but not CHECK
constraints, so a migration that names one differently from its model goes
unnoticed. That is how every CHECK constraint came to be named twice over,
"ck_users_ck_users_issuer_not_empty" (fixed in 0009). This compares the
names the models render with the names Postgres has, table by table. It
does not compare what the constraints check; the behaviour tests do that.
"""

import re

from sqlalchemy import Engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from openlarder.models import Base


def _model_names() -> dict[str, set[str]]:
    names: dict[str, set[str]] = {}
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        names[table.name] = set(re.findall(r"CONSTRAINT (\S+) CHECK", ddl))
    return names


def test_check_constraint_names_match_the_models(engine: Engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conrelid::regclass::text, conname FROM pg_constraint"
                " WHERE contype = 'c' AND connamespace = 'public'::regnamespace"
            )
        ).all()
    database: dict[str, set[str]] = {}
    for table, name in rows:
        database.setdefault(table, set()).add(name)
    models = {table: names for table, names in _model_names().items() if names}
    assert database == models


def test_no_name_carries_its_prefix_twice(engine: Engine) -> None:
    with engine.connect() as conn:
        doubled = (
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint"
                    " WHERE connamespace = 'public'::regnamespace"
                    " AND conname ~ '^(ck|uq|fk|pk|ix)_.*_(ck|uq|fk|pk|ix)_'"
                )
            )
            .scalars()
            .all()
        )
    assert doubled == []
