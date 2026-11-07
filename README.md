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

### Sign-in

Sign-in goes through Authentik at `auth.openlarder.com` (see
[SCOPING.md](SCOPING.md#sign-in)). Without these variables the site runs with
sign-in off, and `/api/auth/login` answers 503. With some but not all of them,
the app refuses to start and names the ones missing.

| Variable | Value |
| --- | --- |
| `OPENLARDER_OIDC_ISSUER` | `https://auth.openlarder.com/application/o/openlarder/` |
| `OPENLARDER_OIDC_CLIENT_ID` | From the OpenLarder provider in Authentik |
| `OPENLARDER_OIDC_CLIENT_SECRET` | From the same page. Never committed |
| `OPENLARDER_SESSION_SECRET` | Any long random string, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The same on every instance |
| `OPENLARDER_PUBLIC_URL` | `https://openlarder.com` in production. Unset locally |

`OPENLARDER_PUBLIC_URL` matters behind Coolify's proxy: the app sees plain
http there, so without it the callback URL it sends would be `http://` and
Authentik, which matches redirect URIs exactly, would refuse it. Authentik
accepts three: `/api/auth/callback` on `localhost:5173`, `localhost:8000` and
`openlarder.com`. A new address needs adding there first.

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
CI (`.github/workflows/ci.yml`) runs the same checks plus a build of the image.

Once per clone, turn on the repo's git hooks:

```sh
git config core.hooksPath .githooks
```

`pre-push` refuses to push to a branch whose pull request has already merged.
It needs `gh`, and lets the push through when `gh` is missing or offline.

House rules for working here are in [CLAUDE.md](CLAUDE.md); reporting a
security problem is in [SECURITY.md](SECURITY.md).
