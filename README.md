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

Sign-in goes through Authgear Cloud at `auth.openlarder.com` (see
[SCOPING.md](SCOPING.md#sign-in)). Without these variables the site runs with
sign-in off, and `/api/auth/login` answers 503. With some but not all of them,
the app refuses to start and names the ones missing.

| Variable | Value |
| --- | --- |
| `OPENLARDER_OIDC_ISSUER` | `https://auth.openlarder.com`, with no trailing slash: it is compared exactly |
| `OPENLARDER_OIDC_CLIENT_ID` | From the OpenLarder application in Authgear |
| `OPENLARDER_OIDC_CLIENT_SECRET` | From the same page. Never committed |
| `OPENLARDER_SESSION_SECRET` | Any long random string, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The same on every instance |
| `OPENLARDER_PUBLIC_URL` | `https://openlarder.com` in production. Unset locally |

`OPENLARDER_PUBLIC_URL` matters behind Coolify's proxy: the app sees plain
http there, so without it the callback URL it sends would be `http://` and
Authgear, which matches redirect URIs exactly, would refuse it. Authgear
accepts three: `/api/auth/callback` on `localhost:5173`, `localhost:8000` and
`openlarder.com`. A new address needs adding there first.

### Internet Archive

Each web recipe's page is copied to the Internet Archive when it's added
(`archive.py`). That works without these, as an anonymous visitor with lower
limits; set both to use an archive.org account's API keys instead. Both or
neither: with one alone, they're ignored.

| Variable | Value |
| --- | --- |
| `OPENLARDER_ARCHIVE_ACCESS_KEY` | From https://archive.org/account/s3.php, signed in to the account |
| `OPENLARDER_ARCHIVE_SECRET_KEY` | From the same page. Never committed |
| `OPENLARDER_ARCHIVE_WEB_PAGES` | `true` unless set; `false` stops web recipes asking the Internet Archive for a copy, for throwaway checks |

Signing out goes on to Authgear's end-session endpoint, which returns people
to `https://openlarder.com/`. That address is registered in Authgear as a
post-logout redirect URI; an address that isn't is sent to Authgear's own page
instead.

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
CI (`.github/workflows/ci.yml`) runs the same checks plus a build of the image,
and the accessibility check below.

The accessibility check (`web/a11y/check.mjs`) runs every kind of page through
axe-core's WCAG 2.1 AA rules in light and dark, and checks phone width. It adds
a sample catalog through the API, so give it a throwaway database and an app
with archiving off:

```sh
docker compose exec -T db psql -U openlarder -d postgres -c "CREATE DATABASE openlarder_a11y"
docker run -d --name openlarder-a11y --network openlarder_default -p 8001:8000 \
  -e OPENLARDER_DATABASE_URL=postgresql+psycopg://openlarder:openlarder@db:5432/openlarder_a11y \
  -e OPENLARDER_ARCHIVE_WEB_PAGES=false openlarder-api
docker compose exec -T db psql -U openlarder -d openlarder_a11y < web/a11y/users.sql
cd web && A11Y_BASE=http://localhost:8001 npm run a11y
```

It needs Chrome (`CHROME` points at it if it isn't where the script looks).

Once per clone, turn on the repo's git hooks:

```sh
git config core.hooksPath .githooks
```

`pre-push` refuses to push to a branch whose pull request has already merged.
It needs `gh`, and lets the push through when `gh` is missing or offline.

House rules for working here are in [CLAUDE.md](CLAUDE.md); reporting a
security problem is in [SECURITY.md](SECURITY.md).
