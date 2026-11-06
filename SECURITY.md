# Security policy

OpenLarder is a public index of the recipes in cookbooks: a FastAPI service on
Postgres with a Vue front end. Today it serves a health check and nothing else;
accounts, contributions, moderation and the public API are being built. This
policy will grow with them.

## Reporting a vulnerability

**Use GitHub's private vulnerability reporting**, on the
[Security tab](https://github.com/rptetzloff/OpenLarder/security/advisories/new).
It opens a private thread with the maintainer and can become a published
advisory when the fix ships.

Please don't open a public issue for anything exploitable before there is a
fix, because an issue publishes it to everyone first. Anything listed below as
known is fine to raise publicly.

There is no bug bounty and no payment. This is a personal project with one
maintainer, and the honest expectation is a first reply within a week rather
than within a day. You'll get credit in the advisory if you want it.

## Supported versions

The deployed site is the only supported version. There are no release
branches and no backports: the fix lands on `main` and deploys.

## In scope

- **Anything that lets one person act as another**, or act above their trust
  level, once accounts exist: publishing without review, reverting or merging
  without the right level, reaching another user's private lists, or curating
  an author page without being verified as that author.
- **Edit history.** Every change to the catalog is meant to be recorded and
  revertible. A way to change a record without leaving a revision is a finding.
- **Cross-site scripting**, anywhere user-written text is shown: reviews,
  notes, descriptions, ingredient names and aliases.
- **The container and its configuration**, as published in this repository.

## Known and documented, not vulnerabilities

- **The catalog is public on purpose.** Books, recipes, page numbers and
  ingredients are open data under the ODbL, and reading or bulk-downloading
  them is the point.
- **`/readyz` reports the database's reachability and the schema revision.**
  Both are operational facts with no secret in them.
