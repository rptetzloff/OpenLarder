# To do

What's left, in rough order. SCOPING.md says what OpenLarder is and why;
this says what isn't built yet. Every PR updates it: tick off what it
finishes, with the PR number, and add what it finds. *Ray, 2026-11-08.*

## MVP

- [ ] **Author pages**: each author's books, co-authors and links; Wikidata
      facts (born, nationality, website) after. Credits and roles exist; the
      page doesn't.
- [ ] **Recipe tags** (course, cuisine, diet): the tables exist, with nothing
      to set or show them. Book-level tags are inherited by its recipes.
- [ ] **Bookshop.org affiliate links**: the purchase_links table exists, with
      nothing to fill or show it.
- [ ] **Read-only public API**: the routes are public and documented at
      `/api/docs`; API keys, rate limits and periodic data dumps aren't built.
- [ ] **Ingredient data**: link canonical ingredients to FoodData Central
      and Wikidata (aliases, hierarchy; allergens are Phase 2).
- [ ] **Contributions**: review queue, edit history and the ODbL contributor
      agreement, together, then trust levels and a report button. Until then
      only admins add to the catalog. The ingredient matching flow's
      suggestions and "new ingredient" step wait on this too.

## Found along the way

- [ ] **Books page at scale**: it loads every book and filters in the
      browser; past a few hundred it needs server-side paging (the API's `q`
      exists, from #50).
- [ ] **Merge two books**: the local catalog has two "The How can it be
      gluten free cookbook" works differing only in case, and nothing can
      merge them.
- [ ] **Long-lived caching for the build's hashed files**: optional; a 404
      for a missing one is already never cached (#42).

## Before launch

- [ ] **Catalog reset script**: empties the catalog tables, keeps the
      schema, accounts and the seeded diets, so the household index can be
      imported again.
- [ ] **Typo fixing in the importer** ("Lemon Jucie"): fix when the match is
      close enough, otherwise suggest and flag, with a measured threshold.
- [ ] **#17**: sign-in and account screens that look like OpenLarder.
- [ ] **Close #26 and #32**: built in #41 and #36; they stayed open because
      PRs merge into `dev`.
- [ ] **Ray**: publish the Google sign-in consent screen.
- [ ] **Ray**: Cloudflare Browser Cache TTL to "Respect Existing Headers".

## Open decisions

- [ ] Authgear's sign-in link and code: how long they last, and whether they
      can be reused.
- [ ] Lawyer review of the privacy policy, terms, content rules, licence and
      allergen notice.
- [ ] USPTO check on "Open Larder" (Classes 9 and 42).
- [ ] How an author is verified.
- [ ] Licence for author bios.
- [ ] Which sources author photos may come from, and under what licence.
- [ ] Grocery partner and its API terms (Phase 2).
- [ ] Entry rules still to settle: blackstrap molasses, ground versus whole
      spices and fresh versus dried, naming the rice where it matters, Greek
      yogurt.

## Later phases

Phase 2 and 3 are listed in SCOPING.md, "MVP vs later phases": shopping
links, saves and reviews, personal shelves, allergen data, meal planning,
OCR import of index pages, magazines and web sources, the write API.

## Done recently

- [x] Search by what you have across several books, closest to made first;
      type-to-find books (#50)
- [x] Book picker on Search (#49)
- [x] Substitutions, with seeded diets (#48)
- [x] Search by recipe title; filter the book list (#47)
- [x] Book editor: title, credits, editions (#46)
- [x] A book's most-used ingredients; search within a book (#45)
- [x] Ingredient hierarchy, set from the ingredient page (#44)
- [x] Search by several ingredients (#43)
- [x] Missing assets' 404 never cached (#42)
- [x] Entry-rule detector for ingredient lines (#41)
- [x] Rename, merge and delete ingredients (#40)
- [x] Canonical ingredients and the Ingredients pages (#39)
