# To do

What's left, in rough order. SCOPING.md says what OpenLarder is and why;
this says what isn't built yet. Every PR updates it: tick off what it
finishes, with the PR number, and add what it finds. *Ray, 2026-11-08.*

## MVP

- [ ] **Site design.** *Ray, 2026-11-08: "not most important for
      development, but definitely part of MVP".* The pages work but aren't
      designed: a real home page (it still shows the placeholder's database
      status), the look (type, colour, logo use, light and dark), navigation
      as sources, search and the larder arrive, and the phone layout. #17's
      sign-in screens should match it.
- [ ] **Wikidata facts on author pages** (born, nationality, website). The
      pages themselves are built (#52).
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

## Planned features

- [ ] **Sources, not just books.** *Ray, 2026-11-08: "a source could be a
      book or a blog or an instagram post or a tv episode or a magazine
      article".* **Step 1 done (#55):** books are sources. **Step 2, websites
      (#56):** a website is a source, one per site, optionally a
      subscription site, with recipes on its pages by address. The
      Internet Archive copy of each web page (#57). **Magazines and
      newspapers (#60):** recipes in issues, at a page. Next: TV shows,
      podcasts and video channels (episodes); then social media posts and
      packaging; then family recipes, with private recipes and sharing. Decided (Ray, 2026-11-08):
      - **Every kind people document is offered**: books, magazines, blogs
        and websites, social media posts, TV and video. Social media is one
        generic kind, an account's post by address, not a kind per
        platform; nothing is built for TikTok in particular (Ray). Also,
        all agreed (Ray, 2026-11-08): video channels (a channel's videos,
        maybe a time), podcasts (a show's episodes), newspaper food sections
        (a paper's dates and pages), subscription recipe sites (websites
        behind a paywall, linked, never copied), packaging (a product's
        label), and **family recipes** (cards, community cookbooks, class
        handouts), which **can be marked private**: seen only by the person
        who added them and whoever they share with, as with the larder.
        Adding one is voluntary, and only its title and ingredient names
        are kept, never amounts or method, so the realistic exposure is a
        "secret ingredient". So the form says plainly what the site keeps
        and who sees it, public unless marked private, and asks the person
        to tick that they understand before it saves (Ray, 2026-11-08,
        between a warning and a tick box; the tick box is Claude's pick, as
        it records the choice).
      - **Each kind has its own shape**, in levels: a book's editions and
        pages; a magazine's issues and pages; a website's posts, by address;
        a social media account's posts; **a TV show's episodes, where the recipe
        belongs** (Ray), maybe with a time in it.
      - **A web page that disappears** is marked archived and links to the
        Internet Archive's copy from when it was added. Adding a web source
        asks the Archive to save the page then (its Save Page Now service),
        and keeps the snapshot's address; if that fails, the Archive's
        nearest earlier copy is looked up instead. To check when built:
        the Archive's current terms and limits, and which social media
        pages archive at all.

      *Claude's recommendation on storage:* real columns and tables per
      kind, not a JSON blob. A source (kind, title, credits) has parts (an
      edition, issue, episode or post, each with its own fields), and a
      recipe sits in a part at a page, a time or an address. JSON only for
      the odd field a kind needs and nothing searches by. Columns keep
      search, constraints and the API documentation honest; a JSON field
      hides typos and can't be indexed cheaply. Settle it before launch:
      renaming Work to Source after would change the public API and every
      `/books/…` link. Books stay first-class: Open Library, ISBNs and
      affiliate links are theirs alone.

      Only books come from Open Library, and only books have affiliate
      links. Everything else stays as it is: the entry rules, ingredient
      lines, search, substitutions and the larder all hang off the recipe,
      not the source. The content rules matter more for web sources: an
      entry links to the recipe and never copies it. *Claude's
      recommendation:* settle the model before launch, renaming Work to
      Source with a kind and Edition to a printing (or issue), even if only
      books are offered at first. Renaming after launch would change the
      public API and every `/books/…` link. Open: which kinds to start with,
      what to store for a web page that disappears, and whether a TV recipe
      is the episode or the show.
- [ ] **Personal larder: your own inventory lists.** *Ray, 2026-11-08.* Each
      person keeps lists named and arranged their own way ("Pantry", "Spice
      drawer", "Refrigerator", "Freezer", or whatever they like). An item is
      a name of their own ("Cholula Chipotle") and the canonical ingredient
      it matches ("Hot Sauce"), so 34 hot sauces are still hot sauce. It
      feeds Search's "what can I make with what I have": your larder becomes
      the ingredients you have. Private by default; shareable with friends
      and family; public if someone wants it. To settle when it's built:
      - whether an item can match a specific kind ("Chipotle Hot Sauce")
        with the broader one counting through the hierarchy, or only the
        top-level ingredient;
      - "out of" or "running low" on an item, with no amounts (amounts stay
        out, as for recipes);
      - how friends and family link: invite by account, a shared household
        larder, or both; and whether shared means view or edit;
      - whether a book shelf ("books I own", Phase 2) lives alongside it.

## Found along the way

- [ ] **Merge two books**: nothing can merge two records of one book yet.
      (The two "How can it be gluten free" books are volumes 1 and 2, not a
      duplicate; the second's title needs "Volume 2", in the book editor.)
- [ ] **Long-lived caching for the build's hashed files**: optional; a 404
      for a missing one is already never cached (#42).

## Before launch

- [ ] **Catalog reset script**: empties the catalog tables, keeps the
      schema, accounts and the seeded diets, so the household index can be
      imported again.
- [ ] **Typo fixing in the importer** ("Lemon Jucie"): fix when the match is
      close enough, otherwise suggest and flag, with a measured threshold.
- [ ] **#17**: sign-in and account screens that look like OpenLarder.
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

- [x] SCOPING.md caught up: site design, private family recipes and
      sources beyond books in the MVP; the data model's kinds of place (#61)
- [x] Magazines and newspapers as sources: recipes in issues, named as the
      cover names them or by date, at a page (#60)
- [x] Sources page at scale: searched on the server, a hundred at a time;
      the swap form's book list became a book finder (#59)
- [x] Merge two authors from the author page, which lists others with the
      same name; a typed name now matches Open Library's authors too (#58)
- [x] Ray: archive.org account and keys in Coolify
- [x] Web recipes' pages copied to the Internet Archive when added; a page
      marked gone offers its copy (#57)
- [x] Websites as sources: add a site, recipes on its pages by address,
      subscription sites (#56)
- [x] Books become sources: tables, API (`/api/sources`) and pages
      (`/sources/…`; old `/books/…` links redirect); books the only kind so
      far (#55)
- [x] Check Open Library: a book's differences from Open Library now, taking
      only those ticked; Open Library's names cleaned on the way in; test
      queries time out (#53)
- [x] Author pages: books, co-authors, links, fixing an author; the
      authors list; names on book pages link to them (#52)
- [x] TODO.md (#51); #26 and #32 closed
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
