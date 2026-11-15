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

### Which site this is

| Variable | Value |
| --- | --- |
| `OPENLARDER_ENVIRONMENT` | `production` on the live site. Anything else (`development` unless set, `staging`) shows a band above the header on every page saying it's that site |
| `OPENLARDER_NOTICE` | Optional. A line of plain text shown in that band instead, in any environment, production included: "Down for maintenance at 9pm" |
| `OPENLARDER_META_TAGS` | Optional. `<meta>` tags for every page's head, as JSON by name, for site verification: `{"impact-site-verification": "56d10364-..."}` (Barnes & Noble's affiliate programme, through Impact). Each is written first in the head with the standard `content`, except Impact's, which is written with `value` alone, as its snippet has it |

### Analytics

Page views are counted with a self-hosted [Umami](https://umami.is)
(analytics.py). Without these settings nothing is counted; one without the
other, and the app refuses to start.

| Variable | Value |
| --- | --- |
| `OPENLARDER_UMAMI_SCRIPT_URL` | The tracker's address on the Umami server, `https://<umami host>/script.js` |
| `OPENLARDER_UMAMI_WEBSITE_ID` | The site's id in Umami (Settings → Websites → the site's tracking code shows it) |

A browser asking not to be tracked (Do Not Track or Global Privacy Control)
never loads the tracker. A page view sends the path only (no query string,
invite links as /invite), no page title, and the referring site's address
only. A sign-in sends one event more, "sign-in", saying whether the account
is new or returning and no page: the callback marks the address it goes to
(`#signed-in=new`) and the loader takes the mark off, so no cookie is set
for it. The privacy page names the Umami host when it's set.

### Sign-ups from ads

Google Ads can be told which ad clicks led to a new account, with none of
Google's script on the site (adclicks.py; *Ray, 2026-11-13*). Off unless
set.

| Variable | Value |
| --- | --- |
| `OPENLARDER_AD_CLICKS` | `true` to switch it on; `false` unless set. It needs `OPENLARDER_SESSION_SECRET`, which signs its cookie: without that the app refuses to start |

Switched on: an ad's click id (`?gclid=`, `gbraid` or `wbraid`) on a
page's address is kept in the cookie `ol_ad_click` for 90 days; a new
account made by that browser in that time adds one row to `ad_conversions`
(the click id, when it was clicked, the minute the account was made, and
nothing that says which account); the row is deleted 90 days later. The
privacy page says all this only while it's on.

Nothing is kept for a browser sending `Sec-GPC: 1` or `DNT: 1`, for
someone signed in, or for a visitor in the EEA, the UK or Switzerland.
The country is Cloudflare's `CF-IPCountry` header, **and without it
nothing is kept at all**: Cloudflare's IP Geolocation (Network → IP
Geolocation) has to be on, and a test from a machine that isn't behind
Cloudflare has to send the header itself.

Setting it up, in order:

1. **Google Ads.** Auto-tagging on (Admin → Account settings). A
   conversion action for offline conversions: category Sign-up, named
   `OpenLarder sign-up` exactly, count One, click-through window 90 days.
   Leave those countries out of the campaigns too. Wait four to six hours
   before the first import.
2. **The role.** Once, as a superuser, after migration 0075:
   `psql "$SUPERUSER_URL" -v role=ads_exporter -v password="$ADS_DB_PASSWORD" -f scripts/ads_role.sql`.
   It may read `ad_conversions` and mark a row exported, and nothing else.
3. **The sheet.** One tab, with this header row, shared only with the
   Google account that owns the Google Ads connection:
   `gclid | gbraid | wbraid | conversion_name | conversion_time | order_id`.
4. **n8n, every six hours**, as `ads_exporter`, with the two statements in
   `scripts/ads_export.sql`: run `pending`; append its rows to the sheet;
   then run `exported` once for each row the sheet confirmed, with its
   `order_id`. Once a day, delete the sheet's rows older than 90 days.
   The statements are tested as that role; the workflow around them isn't
   something this repo can run.
5. **Google Ads again.** Connect the sheet as a data source (Tools → Data
   manager), map the columns, and schedule the import. `conversion_time`
   is written as `2026-11-13 16:03:00+00:00`, UTC; if the mapping wants
   another format, change it in `pending`.
6. **Switch it on**, then check: `curl -si "https://openlarder.com/?gclid=TeSt_abc-123456" | grep -i set-cookie`
   shows `ol_ad_click`; with `-H "Sec-GPC: 1"`, or a malformed id, it
   shows nothing. Google refuses a made-up click id, so the whole path is
   checked with one real click on an ad and a new account.

### Data dumps

The weekly ODbL dumps (dumps.py) go to S3-compatible object storage, and
/data links them. Without these settings there are no dumps; with some but
not all, the app refuses to start.

| Variable | Value |
| --- | --- |
| `OPENLARDER_DUMPS_ENDPOINT` | The store's API address. For Cloudflare R2, `https://<account id>.r2.cloudflarestorage.com` |
| `OPENLARDER_DUMPS_BUCKET` | The bucket, e.g. `openlarder-data` |
| `OPENLARDER_DUMPS_ACCESS_KEY` | An access key that can write to the bucket. For R2: an R2 API token with Object Read & Write on that bucket gives this and the next |
| `OPENLARDER_DUMPS_SECRET_KEY` | Its secret. Never committed |
| `OPENLARDER_DUMPS_PUBLIC_URL` | Where the bucket is read from: its custom domain (`https://data.openlarder.com`) or its `r2.dev` address |
| `OPENLARDER_DUMPS_REGION` | `auto` unless set, which R2 wants; another store's region otherwise |
| `OPENLARDER_TRUST_RECIPES` | Approved recipes that make a contributor trusted, `250` unless set (with the next, both needed) |
| `OPENLARDER_TRUST_BOOKS` | Different books those approved recipes are in, `5` unless set |
| `OPENLARDER_DUMPS_KEEP_DAYS` | How long a dump is kept, `365` unless set (at least 7). Older ones are deleted from the bucket and `/data`; the newest always stays |

The bucket needs public reading (R2: a custom domain or the r2.dev address
under the bucket's Settings). The access key needs to delete too, which R2's
Object Read & Write does.

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

### FoodData Central

Ingredients link to USDA FoodData Central's generic foods, kept in the
database. An administrator loads them from Admin › FoodData Central, or in
the app's container:

    python -m openlarder.fdc load

That downloads the files in `OPENLARDER_FDC_DATASETS` (JSON list; the
defaults are the Foundation, SR Legacy and survey CSV zips current in
November 2026). USDA publishes new Foundation and survey releases under new
file names, from https://fdc.nal.usda.gov/download-datasets; set the new
names and load again. Foods are updated in place and never removed.

### Emptying the catalog

To import the household index again from scratch, in the app's container
(Coolify's terminal for it):

```sh
python -m openlarder.reset                # the catalog
python -m openlarder.reset --everything   # and every account, group and request
```

It lists what it would delete and asks for the site's host name
(`OPENLARDER_PUBLIC_URL`'s, so `openlarder.com`); anything else deletes
nothing. The catalog reset deletes everything in the catalog, family
collections included, with people's larder items, the catalog's edit
history, flags, reports, suggested changes and import history; accounts,
groups, larder lists and requests (unlinked, to link again as their books
come back) stay. `--everything` deletes those too, with all edit history and
the list of published data dumps: only the tag list and the schema's version
are left. After it you sign in as a new user, so make yourself owner again
by hand (`roles.py` has the statement). There's no undo: run a backup first
(Coolify's backups of the database, to their private R2 bucket; the data
dumps are no backup).

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
axe-core's WCAG 2.1 AA rules in light and dark, and checks that none scrolls
sideways on a 360px touch screen or breaks an ordinary word in two. It adds
a sample catalog through the API, so give it a throwaway database and an app
with archiving off:

```sh
docker compose exec -T db psql -U openlarder -d postgres -c "CREATE DATABASE openlarder_a11y"
docker run -d --name openlarder-a11y --network openlarder_default -p 8001:8000 \
  -e OPENLARDER_DATABASE_URL=postgresql+psycopg://openlarder:openlarder@db:5432/openlarder_a11y \
  -e OPENLARDER_ARCHIVE_WEB_PAGES=false -e OPENLARDER_AD_CLICKS=true \
  -e OPENLARDER_SESSION_SECRET=only-for-this-check openlarder-api
docker compose exec -T db psql -U openlarder -d openlarder_a11y < web/a11y/users.sql
cd web && A11Y_BASE=http://localhost:8001 npm run a11y
```

Ad clicks are on so that the privacy page is the one that says so, the longer
of its two; the check fails if it finds the other. It needs Chrome (`CHROME`
points at it if it isn't where the script looks), and
takes about a minute with four browsers at once (`A11Y_WORKERS` for another
number).

For speed, `scripts/perf/scale.sql` turns a copy of the catalog into one the
size of production's (every recipe 19 more times), and `scripts/perf/bench.sh`
times the search endpoints for any images against it. Local figures are a
fraction of production's, whose CPUs are slower; compare images, not numbers.

```sh
docker compose exec -T db psql -U openlarder -d postgres -c "CREATE DATABASE openlarder_perf"
docker compose exec -T db sh -c "pg_dump -U openlarder openlarder | psql -q -U openlarder -d openlarder_perf"
docker compose exec -T db psql -U openlarder -d openlarder_perf < scripts/perf/scale.sql
sh scripts/perf/bench.sh openlarder-api:latest
```

Once per clone, turn on the repo's git hooks:

```sh
git config core.hooksPath .githooks
```

`pre-push` refuses to push to a branch whose pull request has already merged.
It needs `gh`, and lets the push through when `gh` is missing or offline.

House rules for working here are in [CLAUDE.md](CLAUDE.md); reporting a
security problem is in [SECURITY.md](SECURITY.md).
