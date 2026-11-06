# OpenLarder: Scope

Nov 6, 2026 · @Raymond Tetzloff

This is a living document. A decision goes in here as part of the change that makes it, with who decided and when. A decision that gets overturned stays, marked as superseded, with a note on what changed.

## Overview

A free, public, crowdsourced index of recipes in cookbooks and other sources: what's in each book, on which page of which edition, with normalized ingredients, links to buy the book or the ingredients, and an open API. Name: OpenLarder (openlarder.com and openlarder.org). Hosting: self-hosted on Coolify to start.

**Positioning vs Eat Your Books.** EYB does the core indexing well but is a paid membership with a closed catalog. This site competes on four things EYB doesn't offer together:

- Free to use, funded by affiliate links
- Ingredient shopping links (book to recipe to cart)
- Open data and a public API
- A modern, fast, mobile-first experience

**Principles**

- Index, don't reproduce: never store a book's instructions or headnotes
- Ingredients are first-class data, normalized from day one
- Every contribution is versioned and reversible
- The catalog is a public good; the license guarantees it stays open

## Business model

Free for everyone; revenue comes from affiliate commissions on books and groceries. No paywall, no premium tier at launch.

| Stream | Partners | Notes |
| --- | --- | --- |
| Cookbook purchases | Bookshop.org, Amazon Associates | Link per Edition (ISBN). Amazon closes accounts without 3 qualifying sales in the first 180 days, so add it once there's traffic. Bookshop.org first. |
| Ingredient purchases | Instacart (or similar) | Recipe page builds a cart from its normalized ingredients. Confirm current affiliate/API terms. |
| Open API | None at launch | Free with rate limits. Possible paid tier for heavy commercial use later. |

Hosting cost should stay low enough that affiliate revenue only needs to cover infrastructure early on.

## Content rules

The site stores facts about recipes, never the recipes themselves. Book text stays in the book.

| Stored | Not stored |
| --- | --- |
| Recipe title, page number per edition | Instructions or method |
| Ingredient list (normalized) | Headnotes, intros, author descriptions |
| Tags: course, cuisine, diet, technique | Photos from the book |
| Link to the recipe if the publisher posted it online | Scanned pages |

**User content (allowed, user-authored only)**

- Descriptions in the user's own words
- Reviews and ratings
- Likes, saves, "want to cook" lists
- Cooking notes and substitutions

**Risk:** users will paste headnotes or instructions from books. Moderation and a report button handle this; a similarity check against known book text is a later option.

## Data model

A Recipe belongs to one Work (the book); its page number lives on Recipe Page, one row per Edition it appears in, so one recipe entry covers every printing.

![OpenLarder data model: 10 catalog entities, 3 community](DATA_MODEL.svg)

Ingredient lines keep the book's original text and point to one canonical Ingredient, which carries the shopping term and a parent for broader search. On the book page, editions show as tabs or subpages with their own page numbers and purchase links.

Tags set on a Work (such as a diet focus like Gluten-Free) are inherited by every recipe in it, in addition to any tags set on the recipe itself.

A Recipe Ingredient holds one or more ranked Ingredient Options. Each option points to either a canonical Ingredient or another Recipe (a sub-recipe, such as a flour blend used throughout a gluten-free book). Sub-recipe links let users jump to the component recipe and its page, and shopping lists expand them into their own ingredients.

Most lines have a single option. A line the book prints as "grapeseed oil or olive oil" has two: grapeseed oil first, then olive oil as the fallback. "Cheddar or any cheese" works the same way, even though cheddar sits under cheese in the hierarchy. When the book gives each option its own quantity, the option carries it. Shopping lists use the first option. *Decided by Ray, 2026-11-06, because books print lines like this often.*

*Superseded 2026-11-06: a Recipe Ingredient used to point at one target directly. Migration 0002 moved each line's target onto a single first-choice option.*

**Substitutions**

A Substitution says one thing can stand in for another: an ingredient or a recipe on either side, for a stated reason, usually a diet ("vegan butter for butter, dairy-free"). It can link two flour blends from different books. It is catalog data under the ODbL, separate from the free-text cooking notes users write. Each substitution records where it came from: printed in a book (work and page), or contributed. *Decided by Ray, 2026-11-06: most of the books in the first import are allergen-free in some way, so this gets heavy use.*

**Allergen data**

Ingredients carry allergen data (contains dairy, gluten, egg). This lets the site offer substitutions for a diet automatically, not only where someone has entered one. *Decided by Ray, 2026-11-06, on the condition that it is presented as crowdsourced information.*

- Wherever allergen data or a diet-based suggestion appears, a notice says it is crowdsourced and unverified, and that it is not a guarantee a recipe is safe for anyone.
- The site never labels a recipe "safe for" an allergy. It can say what the catalog records about the ingredients, and nothing more.
- Allergen data describes an ingredient in general, not any product. Oats may or may not be processed alongside wheat, and one brand's stock may contain milk when another's doesn't. The notice says so.
- The wording of the notice is written with the feature and reviewed by a lawyer along with the content rules.

## Ingredient normalization

Every ingredient line resolves to one canonical ingredient plus optional form, prep, and quantity. Search, shopping, and the API all depend on this.

**Structure**

- **Canonical ingredient:** one record per real thing ("green onion")
- **Aliases:** names that resolve to it ("scallion", "spring onion"), with optional region (US/UK/AU)
- **Hierarchy:** parent links for broad search ("aged cheddar" → cheddar → cheese)
- **Form and prep:** stored on the recipe line, not the ingredient ("diced", "canned", "toasted")
- **Shopping term:** what to search for at the grocer, which can differ from the name

**Seeding**

Start from an existing dataset rather than an empty table. Candidates: USDA FoodData Central, the FoodOn ontology, Wikidata food items. Pick one as the base and map the others to it over time.

**Matching flow**

1. Contributor types an ingredient line as written in the book
2. Parser splits quantity, unit, prep, and name
3. Fuzzy match suggests canonical ingredients as they type
4. Contributor picks one, or flags it as new
5. New ingredients go to a moderation queue to be approved, merged, or mapped as an alias

The original text line is kept alongside the match, so mappings can be corrected later without re-entry.

## Contributions and moderation

Modeled on OpenStreetMap and Wikipedia: anyone can contribute, everything is versioned, and trust is earned.

**What users can submit**

- New books and editions (prefilled from ISBN lookup)
- Recipe entries for a book: title, page per edition, ingredient lines, tags
- Corrections to existing entries
- New ingredients and aliases (via the matching flow)
- Bulk imports: CSV or spreadsheet of a book's recipes

**Bulk import rules** (decided by Ray, 2026-11-06, from a sample of the household index)

- **Fallbacks are written as the book writes them.** "A or B" and "A, B, or C" inside one ingredient become ranked options in the order written. If splitting a line on "or" leaves a part that matches nothing, the line is flagged instead of split.
- **Sub-recipe references** are written as "Name (p. 14)". A bare number in brackets, "Name (270)", is read the same way.
- **Wrong page in a reference:** link to the recipe with that name in the same book, use that recipe's real page, and flag the mismatch.
- **Reference to a recipe the book doesn't have:** flag it as an unknown ingredient.
- **Tag that reads like a note** ("Measurement Reference on p. 72"): flag it for review.
- **Typos** ("Lemon Jucie", "FreshGinger"): fix them when the match is close enough to be confident. Otherwise suggest a fix and flag it. "Close enough" gets a measured threshold when the importer is built.
- **The same ingredient twice in one recipe** is kept once.

Flags go to the review queue with the reason attached. Bulk imports go through review whatever the contributor's trust level.

**Trust levels**

| Level | How earned | Edits |
| --- | --- | --- |
| New | Signup | Every submission goes to the review queue |
| Contributor | N approved submissions | Edits publish directly; new ingredients still reviewed |
| Trusted | Sustained quality, granted by moderators | Can review others' submissions and merge ingredients |
| Moderator | Appointed | Everything, including bans and reverts |

**Safeguards**

- Full edit history on every record, one-click revert
- Bulk imports always go through review, regardless of trust level
- Duplicate detection on books (ISBN) and recipes (title + work)
- Report button on all user content

## Open API and data licensing

Decision: the catalog is open data under the ODbL (Open Database License), the same license OpenStreetMap uses. Contributors agree to it at signup, before the first public contribution.

**License options**

| License | Effect | Fit |
| --- | --- | --- |
| ODbL | Share-alike for databases; derived databases must stay open | Strong fit, what OpenStreetMap uses |
| CC BY-SA 4.0 | Share-alike, attribution | Works, less database-specific |
| CC0 | Public domain, no conditions | Most permissive; a competitor could take it closed |

Contributors agree at signup that their contributions are licensed under the chosen license. User reviews and descriptions can sit under a separate license (or stay non-exportable) if needed.

**API**

- Read endpoints: works, editions, recipes, ingredients, search by ingredient
- API keys, rate limited, free tier
- Periodic full data dumps so heavy users don't hammer the API
- Write API later, gated by trust level

## Tech stack

Python and Vue, matching the structure of Sederunt and Sennight, self-hosted on Coolify with Docker Compose.

| Layer | Choice | Notes |
| --- | --- | --- |
| Backend | Python, FastAPI + Pydantic | SQLAlchemy + Alembic for migrations; auto-generated OpenAPI docs serve as public API docs |
| Frontend | Vue 3 + Vite |  |
| Database | PostgreSQL | pg\_trgm for fuzzy ingredient matching, built-in full-text search |
| Jobs and cache | Redis + Python worker (arq or RQ) | Bulk imports, Open Library lookups |
| File storage | S3 (existing) | Covers, import files, Postgres backups; separate buckets or credentials for public assets vs backups |
| Auth | Generic OIDC (e.g. Zitadel) | Needs public self-registration and social login |
| Hosting | Coolify (prod), Rancher Desktop with dockerd (dev) | One docker-compose.yml for both; Cloudflare Tunnel for public access |

No multi-tenancy: one public catalog.

## MVP vs later phases

The MVP proves the catalog is useful with a few hundred books indexed; social features and the write API wait.

**MVP**

- Book catalog with works and editions (ISBN lookup, Open Library metadata)
- Recipe entries with page numbers per edition
- Ranked ingredient options (fallbacks) on recipe entries
- Substitutions, entered by hand or printed in a book. Suggesting them automatically for a diet waits on allergen data. *MVP, because the first import's books print their own swaps and would otherwise need entering twice. Ray left the phase to Claude on 2026-11-06, asking only that it be logical.*
- Ingredient normalization with seeded data and the matching flow
- Search by ingredient, by book, by recipe title
- User accounts, submissions, review queue, edit history
- Bookshop.org affiliate links
- Read-only public API

**Phase 2**

- Bulk CSV import
- Ingredient shopping links (Instacart or similar)
- Saves, likes, "want to cook" lists, reviews, user descriptions
- Personal shelf: mark books you own, filter search to your shelf
- Amazon Associates links, once traffic supports it
- Allergen data on ingredients, and substitutions suggested for a diet. *Phase 2 rather than MVP: the MVP's substitutions are entered by hand, and allergen data needs its own seeding and review before anything is suggested from it. Phase chosen by Claude, on the same delegation as substitutions.*

**Phase 3**

- Meal planning and shopping lists
- Photo/OCR import of a book's index pages
- Magazines and web recipe sources
- Write API
- Data dumps on a schedule

## Risks and open decisions

The biggest risk is cold start: a crowdsourced index is empty until someone fills it.

**Risks**

| Risk | Mitigation |
| --- | --- |
| Cold start, empty catalog | Seed a few hundred popular books before launch; recruit early indexers from cookbook communities |
| Ingredient data quality | Seeded base dataset, moderation queue, original text kept for re-mapping |
| Copied book text in user content | Content rules, report button, moderation |
| Affiliate revenue doesn't cover costs | Keep infrastructure lean; no paid services until revenue exists |
| Publisher or author objections | Index only facts; respond to takedown requests promptly |
| Moderator burnout | Trust levels push review work to trusted contributors |
| Someone relies on crowdsourced allergen data and has a reaction | A crowdsourced notice wherever allergen data appears, no "safe for" claims, report button, lawyer review of the notice's wording |

**Open decisions**

- [x] Name and domain: OpenLarder
- [x] Tech stack: Python/FastAPI, Vue, Postgres, Redis, S3 on Coolify
- [x] Data license: ODbL
- [ ] Base ingredient dataset
- [x] Which phase substitutions ship in: MVP (see the MVP list)
- [x] Allergen data on ingredients: yes, presented as crowdsourced (see Allergen data)
- [ ] Grocery partner and its API terms
- [ ] Edition handling when a recipe's page is unknown for an edition
- [ ] Seeding plan: start from the existing 125-cookbook household index (self-built CSV; first bulk import target)
- [ ] USPTO check on "Open Larder" (Classes 9 and 42)

Not legal advice: have a lawyer review the content rules, the license, and the allergen notice before launch.
