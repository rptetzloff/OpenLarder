# House rules

Short on purpose, so they get applied rather than rediscovered.

Gathered on 2026-11-06, at Ray's request, from the house rules of every sibling
repo: `anagrimoire`, `vue-password-generator`, `sennight`, `sederunt`,
`amherstcomm-games`, `AreTheBrewersOnTV`, `AreThePackersUndefeated` and
`are-they-sports`. The rules are the same in all of them; the examples are
not. Most examples below are borrowed and say where from. They are kept because
a rule with no example attached gets skipped. Replace them as this repo earns
its own.

There is no rule count in this heading on purpose. `are-they-sports` keeps one
and needs a test to stop it going stale; the sites say "twelve" and have
thirteen.

## Measure, don't assert

If a claim can be checked against the running thing, check it before writing it
down. The bugs that shipped in the sibling repos all read correctly in the
source: a records page rendered as one tall column at every width for months
because of a flexbox rule nowhere near the grid (`are-they-sports`); a solver
printed the entire dictionary under its answer (`anagrimoire`). All of it
typechecked, linted, and passed the suite of the day.

A test that reads the source proves the source, not the behaviour. Keep both,
and know which one you just wrote.

**Render it and look.** A page claim is checked by rendering the page, before
and after. Below about 500px a headless window lies, because Windows enforces a
minimum width and crops the image. Emulate the device over the DevTools
protocol and ask the page for `document.documentElement.scrollWidth`, and which
element is over (`are-they-sports`).

**Check it where it will run, not where it is convenient.** A working tree, a
venv, a container and a deployment are four environments, and passing in one
says nothing about the others. In `sederunt` an image passed its own
`HEALTHCHECK` while the platform's probe failed, because the image had no
`curl`; a script the readme told people to run was never copied into the image;
a Vite proxy hid an API path change that only the container exposed. If the
instruction is "run this in the container", run it in the container first.

**An edit that silently did nothing is worse than one that failed.** Four
`sederunt` changes were string replacements that matched nothing and were built
on for minutes afterwards. Prefer an edit that errors when its target is
missing; otherwise read the result back.

## Don't jump to conclusions

The failure mode is not being wrong about hard things. It is taking a plausible
reading and stating it as established when the check was one command away. A
run marked `cancelled` was reported as stopped work while its jobs were still
going. A heap measured in isolation was reported as fine; in the server, with
everything else loaded, it was not (`are-they-sports`).

So: **if a claim is checkable in one command, run the command before saying
it.** When it is not, say which kind of claim it is. "The run list says
cancelled" and "the work stopped" are different sentences.

Never pipe a command whose exit code matters: `set -o pipefail`, or do not
pipe. A suite piped through `tail` reported green while red. And a tool's own
report of what it did is a claim, not evidence.

When a control panel and the runtime disagree about what the runtime is doing,
the runtime is right (`sederunt`: a UI put a database on one network, and
`docker inspect` showed another).

**When it cannot be checked from here, ask. Do not caveat and ship.** A required
attribution notice was written from memory, marked "not checked", and
committed. It was wrong, and so were two licence claims beside it
(`are-they-sports`). A disclaimer hands the work to the reader. Asking takes one
message.

## A rule enters this file when somebody decides it

And the entry says who decided it and when. Inferring a rule from what the
codebase happens not to contain is how a habit becomes a constraint nobody
chose. `are-they-sports` described "no client-side JavaScript" as a
long-standing principle in the same commit that invented it.

This repo's own example, from its first day: the first `pyproject.toml` carried
an AGPL licence line that nobody had chosen. It was caught before commit, and
Ray chose Apache 2.0 for the code. The catalog data's ODbL is a separate
decision, recorded in `SCOPING.md`.

## Comments explain why, never what

When a value was chosen by measurement, record the number **and** the rejected
alternative. "5 minutes, not 15: two CSRs booking the same tech mid-call is the
real contention case" is worth more than the constant (`sennight`).

A comment must never assert an outcome the code cannot produce. "This always
yields one or two columns" sat above a grid that yielded one, for months. It
was worse than no comment, because it answered the question a reader would
otherwise have checked (`are-they-sports`).

## Reversals stay visible

When a decision is overturned, mark the old one and say what changed. Do not
quietly edit it away. The trail is why the conclusion is trustworthy; a
document that only ever agreed with itself is not evidence of anything.

## State the limit of the claim

Say what a thing does *not* do, in the same breath. If a guarantee has an
exception, the exception ships next to it. When a claim stops being true,
rewrite it deliberately rather than deleting it.

## Tests assert rules, and fail on the old code

Where a rule can be read out of an artifact, assert it against the artifact.
Where it cannot, exercise the running thing. Either way, verify a new test
fails before the fix, by reverting. A test that never failed has proved
nothing: a sort test using `0001`, `0002`, `0010` passed under the very bug it
was written for, because zero-padding makes lexical and numeric order agree
(`are-they-sports`).

**Know what your checks cannot see.** This repo's: `alembic check` compares
tables, columns, keys and plain indexes, and does not compare CHECK constraints
or expression indexes. Those are covered by tests that insert what the database
should refuse. When one constraint was removed from the migration, its test
went red.

The same blindness hid that every CHECK constraint had been created with its
prefix twice, `ck_users_ck_users_issuer_not_empty`, for eight migrations:
the naming convention applies `ck_<table>_` to whatever name it is given.
`tests/test_constraint_names.py` now compares CHECK constraint names in the
database with the models'. In a migration, name a CHECK constraint with
`op.f("ck_<table>_<name>")`, which marks the name as final.

**A mutation harness needs a control.** The first mutation run in
`are-they-sports` used a command the runner rejected, so every mutant "died" to
an error and it reported a perfect score. Run the unmutated suite under the
exact same command first. A surviving mutant is a claim about the test that
needs checking too.

**Run against an empty database and a loaded one.** They catch different
defects. Assertions written against fixture-only tables became claims about
the whole league once real data arrived, and a test written in the same fix
passed only because the loaded database already had a row it never created
(`are-they-sports`). A test resting on state it did not create is the same
defect either way.

Business rules live in functions that take values and return values, so they
are testable without a database or a request. Side effects (clock, storage,
network, mail) are injected so they can be faked. The exception is a rule the
database itself enforces, which is tested against the database. Most of this
repo's catalog rules are that kind.

A number pinned in two suites is wrong in one of them the day it moves. Exact
counts live in the layer closest to the artifact; every other layer asserts the
relation (distinct, ordered, at least this many), not the snapshot.

**An invariant claimed in a commit message is not an invariant.** If a property
is worth asserting in prose, write the test that fails when it stops being
true.

A test that can hang on its own failure is worse than no test. Put the rollback
in a `finally`, not after the assertion (`sederunt`).

## Derived data stays derived

If it can be rebuilt from sources, rebuild it; never store it and hand-edit.
Two lists that must agree are one list read twice. Here, a recipe's inherited
tags are the `recipe_effective_tags` view rather than copies of the book's tags.
Tagging a book never writes to its recipes.

Round trips are where derivations break, and the break is quiet. Check every
derived output against its source, or check none and say which you did.

## Colour and theme

All colour goes through tokens, never a literal in a component. Every intended
pair is verified by test, 4.5:1 for text and 3.0:1 for control boundaries,
across both themes, because a pair that passes in one can fail in the other.

`tests/test_colour_tokens.py` reads the tokens out of `web/src/App.vue` and
checks each intended pair in both themes. It cannot see a component using a
pair it doesn't list; adding a pair means adding it there. Its first catch,
before it was even committed: the logo's amber with white text is 2.2:1.

## Dependencies default to none

A new runtime dependency needs a reason in the PR. A library that implements a
standard we would otherwise get wrong earns its place; one that saves ten lines
does not. After any install, `npm ci --dry-run` comes back clean and the
lockfile contains what the manifest declares. One sibling's lockfile pinned
`vite` and nothing else for months.

The infrastructure is what `SCOPING.md` names, decided by Ray on 2026-11-06:
Postgres, Redis with a Python worker, and S3. Each arrives with the first
feature that needs it, not before. Redis is not in `docker-compose.yml` until
something queues a job.

## Docs are part of the change, not a follow-up

Every PR checks the documents that make claims about the thing it changes, and
updates the ones the change made wrong: `README.md`, `SCOPING.md`,
`DATA_MODEL.svg`, this file, the module docstrings, and later the content rules,
licence terms and any help text. A claim written when it was true does not
announce that it stopped being true: no test fails, no build breaks. One
sibling's security policy listed a fixed issue as known, which does more than
mislead; it tells researchers not to report it.

Where a claim can be checked mechanically, prefer that to diligence. The
OpenAPI spec is generated from the routes, which is why it cannot drift. Prose
cannot be checked that way, which is what the review pass is for. Run what the
docs tell someone to run, in the place they are told to run it.

Documents answer different readers' questions and need not say the same
things. What they may not do is *disagree*.

## Commits and branches

A subject line that says what the change makes true: "Holds release on the
worker tick rather than on read", not `fix: hold bug`. No conventional-commit
prefixes and no ticket refs. The body is as long as the reasoning needs,
including what was measured and what was rejected.

### Work branches into `dev`. `dev` goes into `main`.

Every change starts on its own branch off `dev` and reaches `dev` by pull
request. Releases are a PR from `dev` into `main`. `dev` and `main` are
permanent; a work branch is deleted when its PR merges. (`anagrimoire` and
`amherstcomm-games` commit straight to `dev` instead. This repo follows
`sederunt` and `are-they-sports`: a work branch buys a reviewable unit and
somewhere to abandon work without rewriting shared history.)

**For now, openlarder.com deploys from `dev`, so a merge into `dev` is a
release.** `main` waits until there is a separate dev site for `dev` to deploy
to. Until then, "merged" means "live", and changes are checked on
openlarder.com after they merge. *Decided by Ray, 2026-11-06.*

- **Merge commits, never squash.** A squashed release left `are-they-sports`
  with 220 commits on `main` that `dev` did not have, and every later release
  PR diffed against the wrong base.
- **Branch from `dev`, never from another work branch.** A stacked PR merged
  seconds after its base, before GitHub retargeted it, and landed on the wrong
  branch.
- **Back-merge `main` into `dev` after each release.** It is a no-op on the tree
  and stops the drift above from accumulating.
- **Check whether the PR has merged before committing to its branch.** Three
  times in `are-they-sports` a push to an already-merged branch succeeded, CI
  went green, and the work was simply not in `dev`. `gh pr view <n> --json
  state` is one command, and `.githooks/pre-push` refuses the push. It is a
  backstop, not the rule: it lets the push through when `gh` is missing or
  offline.

Run whichever suite can catch the change locally before opening a PR. CI is for
confirming, not discovering.

## Files

Extract when a file stops being readable, not at a line count. There are no
known exceptions yet. Both sibling sites' `main.js` files are past 1,400 lines,
are the least-tested files in their repos, and produced both of a year's
production bugs. Keeping it that way here is cheaper than fixing it later.

---

*Repo-specific facts (what is stored and what is not, the data model, what
each phase ships) live in `SCOPING.md`, `DATA_MODEL.svg` and the module
docstrings, not here. If a rule needs a project detail to make sense, the
detail belongs somewhere else.*
