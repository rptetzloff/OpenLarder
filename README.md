# OpenLarder

A free, open index of the recipes in cookbooks: which book, which page of which
edition, and what goes in them. See [SCOPING.md](SCOPING.md) for what it is and
what it is not, and [DATA_MODEL.svg](DATA_MODEL.svg) for the catalog's shape.

The catalog is open data under the ODbL. It stores facts about recipes, never a
book's instructions or headnotes.

## Stack

FastAPI and SQLAlchemy on PostgreSQL 17, migrations by Alembic, and a Vue 3 +
Vite front end. One container serves the API and the built SPA.

## Running it

Postgres in a container, the API from a virtualenv:

```sh
docker compose up -d db          # Postgres on localhost:54320
python -m venv .venv
.venv/Scripts/pip install -e '.[dev]'     # .venv/bin/pip off Windows
cp .env.example .env
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn openlarder.main:app --reload
```

The front end, in another terminal:

```sh
cd web && npm install && npm run dev     # http://localhost:5173
```

Or the whole thing as it deploys, built from the Dockerfile:

```sh
docker compose up --build        # http://localhost:8000
```

`/healthz` answers when the process is up; `/readyz` when it can reach the
database, with the schema revision it is on. The API docs are at `/api/docs`.

## Tests

```sh
.venv/Scripts/pytest
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
cd web && npm run typecheck
```

The tests need the Postgres from `docker compose up db`. Each run creates its
own database beside the configured one, migrates it, and drops it afterwards.
