# To do

What's left, in rough order. SCOPING.md says what OpenLarder is and why;
this says what isn't built yet. Every PR updates it: tick off what it
finishes, with the PR number, and add what it finds. *Ray, 2026-11-08.*

## MVP

- [ ] **Site design.** *Ray, 2026-11-08: "not most important for
      development, but definitely part of MVP".* Ray's wireframes (in
      private/, not committed) draw the home, search, source, recipe,
      ingredient and author pages, adding a recipe, and entering a whole
      book. Decided (Ray, 2026-11-08): light as drawn, dark when the device
      asks; nothing that doesn't work yet is shown, each arriving with its
      feature; one PR per page. **The shell and home page (#66):** colours
      as tokens for light and dark, the full logo top left, the header's
      sections and footer, and the front page's search, "cook with what you
      have" and recently added sources. **Search (#69):** the panel, a
      source-kind filter, result cards with where each recipe is, numbered
      pages. **A source's page (#70):** the admin bar and breadcrumbs, the
      edition tabs, most-used ingredients, and the recipes as a table
      (page, title, first ingredients, components) to filter and sort.
      **A recipe's page (#75):** breadcrumbs, a "Find it in" box (cover,
      source, authors, page with an edition picker, or the issue, episode
      or web page), the ingredients with Copy list, Used in with pages,
      swaps, and flags and actions beside. **The ingredient and author pages
      (#77):** admin bars, breadcrumbs, the ingredient's cards and its
      recipes counting what's under it with each line as written, the
      author's sources as covers and who they're credited with. **Adding a
      recipe (#78):** four steps (source, recipe and where, ingredients,
      review), a box per ingredient line with its check beside it: the
      entry rules with a fix or "keep it", what it will be matched to (by
      another name too), a recipe in the same source it cites, its options,
      and for no match, ingredients named like it; admins see bulk import
      beside it. Left out until they exist: the contributor-agreement tick,
      "Submit for review", your contributions, and an entry-rules page to
      link. **Entering a whole book (#80):** a row per recipe (page, title,
      ingredients), each saving when you leave it, with the line checks as
      chips to fix from, a filter for rows with checks, and page order.
      No "N of 135" yet: nothing records how many recipes a book holds.
      The wireframes' pages are all built. Next, the list pages in the same
      style (Ray, 2026-11-09), one PR each: **Sources (#81):** the add forms
      as panels, a search box, kind filters with counts, sorting by title,
      most recipes or newest, and covers in a grid. **Ingredients (#82):** a
      table with what each comes under and its other names, most used or A
      to Z, and "Top level only" to browse the hierarchy. **Authors (#83):** a
      table with what each is known for (their source with the most
      recipes) and their sources and recipes, people or organisations, A to
      Z or most recipes. Every page is now in the redesigned style. Then the
      admin and account pages, in three PRs (Ray, 2026-11-09): **Admin
      (#87):** one admin band on every admin page and Sources, the current
      page marked; the overview as cards with what's waiting and the
      catch-up tools as panels; flagged recipes and import history as
      tables; suggestions as cards; filters as buttons with counts; My flagged
      recipes, the same page, came with it. **Your account (#88):** cards
      to My flagged recipes and Groups with what's waiting, the name form
      and signing in as panels. **Groups
      (#89):** your groups as a table with Make a group as a panel; a
      group's collections and members as tables, its admin's Rename and
      Delete as buttons, and inviting in a panel beside them; an invite as
      a panel. Every page but Privacy and Terms, which stay a column for
      reading, is now in the redesigned style. **The brand (#98):** the
      kit made with Claude in the chat app for Ray (2026-11-09): its light and dark themes (THEMES.md: larder green,
      terracotta, mustard and ivory; deep greens with ivory, mustard and
      light terracotta), a focus ring, the horizontal logo in
      the header, Outfit served from OpenLarder itself, and the favicons,
      app icons, web manifest and social card. #17's sign-in screens
      should match: Authgear's own theming, with the same colours, logo and
      Outfit.
- [x] **Wikidata facts on author pages** (#90): born and died (years
      only), country and website, from Wikidata's query service, found by
      the author's Open Library ID or a Wikidata item an admin gives on the
      author's page. Admin's "Fetch Wikidata facts" works through every
      author Wikidata could know, 50 to a query, asking again after a month;
      authors who fit an item another author has are listed to merge.
- [ ] **Recipe tags** (course, cuisine, diet): the tables exist, with nothing
      to set or show them. Book-level tags are inherited by its recipes.
      Decided (Ray, 2026-11-09; SCOPING.md, Data model), in three PRs:
      **Chapters (#91):** a recipe's chapter in its book, imported from the
      index's Tag column (running an import again fills it in on recipes
      already there), entered in the recipe form and Enter a whole book,
      shown on the recipe and filtering the book's recipe table. **Tags
      (#92):** courses, cuisines and techniques start the list (migration
      0032; diets came with 0018); whoever may change a source tags it
      and its recipes from "Edit tags", and admins add to the list there;
      tags show as chips that search by them, and search filters by
      them, on their own too. **Tag suggestions (#93):** the queue takes
      kind `tag` (migration 0033, with public views of recipes, tags and
      recipe tags for n8n, granted to its role); accepting tags the
      recipe. Workflow 4 is specified in SCOPING.md for Ray to build in
      n8n. Then this item is done.
- [x] **Bookshop.org affiliate links** (#94): "Buy this edition" on a book's
      page and in a recipe's Find it in box, made from the edition's ISBN,
      with the commission said beside them and a paragraph in the privacy
      policy. Each goes through `/go/bookshop/<edition>`, which counts the
      click (edition, shop, time, page; nothing about who) and skips bots.
      Hidden until `OPENLARDER_BOOKSHOP_AFFILIATE_ID` is set in Coolify
      (Ray, 2026-11-09: no account yet). **More shops (#95):** Barnes &
      Noble, ThriftBooks, Book Outlet, Amazon and Kobo (ebooks, searched by
      title and author), each shown once its setting is in Coolify: Amazon's
      Associates tag (`OPENLARDER_AMAZON_TAG`, with its required wording
      beside its link), and for the others the affiliate network's deep
      link with `{url}` where the shop's address goes
      (`OPENLARDER_BARNES_NOBLE_LINK`, `_THRIFTBOOKS_LINK`,
      `_BOOKOUTLET_LINK`, `_KOBO_LINK`). Audiobook shops left out (Ray).
      The buttons stack beside the cover. **Your shops (#96):** "Choose
      your shops" under them puts them in your order and hides the rest,
      one always left; kept with the account when signed in (migration
      0035), in the browser otherwise. Still to come: a page showing the
      clicks.
- [x] **Read-only public API** (#97): the routes are public and documented
      at `/api/docs`. Without a key, per address: 60 plain reads and 10
      searches a minute, 1,000 requests a day; a free key from Your account
      raises each ten times (Ray, 2026-11-09: start low, loosen with real
      traffic). Each is a setting, `OPENLARDER_API_READS_PER_MINUTE`,
      `_SEARCHES_PER_MINUTE`, `_REQUESTS_PER_DAY` and their `_KEY_` forms,
      and the docs and the keys panel say them as set. A key reads what
      someone signed out sees; writes need an account. The site's own pages
      are never limited. Counts are in memory, so a deploy resets them.
      **Monitoring (#99):** Admin's API usage page lists each outside caller
      by day (a key by its name and owner; no key, by a keyed pseudonym of
      its address and its network, never the address; 30 days, migration
      0037), and revokes any key; Buy-link clicks shows clicks by shop,
      book, page and day (Ray, 2026-11-09).
- [x] **Data dumps** (#113). *Ray, 2026-11-10: object storage; CSV and
      JSON Lines.* Weekly, the public catalog (what someone signed out sees;
      nothing about accounts) as a zip of CSVs and a zip of JSON Lines, each
      with a README giving the ODbL and its attribution, uploaded to
      S3-compatible storage (R2) and listed at `/data`. An administrator can
      build one now from Admin. Needs the `OPENLARDER_DUMPS_` settings.
      Kept a year, then deleted from the bucket and the list (#115; *Ray,
      2026-11-10: 12 months*), `OPENLARDER_DUMPS_KEEP_DAYS` to change it.
      - [ ] Ray: an R2 bucket with public reading, and its API token.
- [ ] **Ingredient data**: link canonical ingredients to FoodData Central
      and Wikidata (aliases, hierarchy; allergens are Phase 2).
- [ ] **Roles** *(Ray, 2026-11-10)*: done (#101). User, contributor,
      moderator, administrator, owner (roles.py), in place of the admin
      and enterer flags. Moderators edit the catalog, work flags and
      suggestions, decline requests and make contributors; administrators
      also run imports, API usage and buy-link clicks and make moderators;
      only the owner makes administrators, and the owner is set in the
      database. People and roles at `/admin/people`.
- [ ] **Contributions** *(Ray, 2026-11-10: "build review first")*: review
      queue, edit history and the ODbL contributor agreement, so a
      contributor's additions wait for a moderator. Ray's calls: first
      books and their recipes; hidden until approved; history of every
      catalog change. In order:
      - [x] Edit history (#102): a trigger records every catalog row added,
        changed or removed, by whom and through what, grouped by request.
        A History panel on each source, recipe, ingredient and author page;
        Recent changes at `/admin/changes` for moderators. Family
        collections' history only with the collection; an ingredient first
        named in a private recipe doesn't say who made it.
      - [x] The contributor agreement and review (#108). Everyone who adds
        to the catalog accepts the agreement first (agreement.py; a new
        version asks again), the owner included. Contributors add books (by
        ISBN or by hand) and recipes to any book; each waits, hidden from
        everyone but them and moderators (site, API, n8n's views, history),
        until a moderator approves it at `/admin/review`, one at a time or
        "approve all". Sent back with a reason, it waits again once changed.
        Approving a book closes its requests. Contributors change only their
        own waiting items, tags included.
      - [ ] A lawyer's read of the agreement's wording, with the terms.
      - [x] Proposed changes to published recipes (#110): a contributor's
        "Suggest a change" sends the edit, checked as a save would be, with
        why; a moderator sees it beside the recipe as it is at
        `/admin/review` and applies it (saved as the contributor's edit,
        through "proposal:<id>") or declines it with a reason. Applying
        after the recipe has changed since needs saying so.
      - [x] The same for sources' details (#112): title, subtitle, credits
        and editions, from "Suggest a change" on a published source's page,
        applied through the same edit a moderator makes. A recipe added to
        the source isn't counted as a change since.
      - [x] One-click revert (#109): a moderator's Undo on any change in a
        record's history or Recent changes puts back what it removed, sets
        back what it changed and takes away what it added, as a new change
        through "revert:<change>", so it can be undone in turn. Refused when
        a later change touched the same records (undo that first), or for a
        removal recorded before migration 0042 kept whole rows.
      - [x] Trust levels (#119). *Ray, 2026-11-10: "the greater of 250
        recipes or 5 books".* A contributor with at least 250 approved
        recipes across at least 5 books is trusted when the approval that
        gets them there is made; what they add then publishes at once (still
        in the history, still undoable; changes to published records still
        go as proposals). Moderators grant or withhold it on People;
        withheld sticks, cleared lets it be earned again. Settings
        `OPENLARDER_TRUST_RECIPES` and `OPENLARDER_TRUST_BOOKS`. The
        contributor agreement says so (version 2026-11-10.2, asked again).
      - [ ] A report button on every public record, for anyone (*Ray,
        2026-11-10*), into a moderators' queue. The ingredient matching
        flow's suggestions and "new ingredient" step wait on this too.
      - [ ] Edit history keeps everything forever: check its size once the
        household index is imported again (~400,000 rows for 19,000 recipes).

- [x] **A band saying which site this is** (#103). *Ray, 2026-11-10.*
      `OPENLARDER_ENVIRONMENT` other than `production` shows one above the
      header on every page; `OPENLARDER_NOTICE` puts a line of your own
      there in any environment. Set `production` on the live site when it
      exists.

- [x] **Search engines' crawlers and the API** (#111). *Ray, 2026-11-10,
      seeing Google's 66.249.x.x on API usage.* Google renders pages with
      the API's data, without the header that marks a page's own requests,
      so it was counted, and would have been limited into indexing empty
      pages. Googlebot, Bingbot and Applebot are now verified by the
      ranges their engines publish (fetched daily; reverse DNS as the
      fallback, which Docker's DNS doesn't answer), never limited, and
      shown by name on API usage. API answers and buy-link redirects say
      `X-Robots-Tag: noindex` (robots.txt can't block /api, or Google
      can't render the pages); robots.txt keeps crawlers off /go/. The
      daily cap now survives a deploy.

- [x] **Analytics with Umami** (#114). *Ray, 2026-11-10: self-hosted; honour
      Do Not Track and Global Privacy Control; path only, secrets removed.*
      A loader in every page's head skips the tracker for DNT or GPC, and
      sends one page view a load by hand: the path without a query string,
      invite links as /invite, no title (a private collection's name is in
      it), the referrer cut to its site. Settings: `OPENLARDER_UMAMI_SCRIPT_URL`
      and `OPENLARDER_UMAMI_WEBSITE_ID`; the privacy page says what's
      recorded and where.

## Planned features

- [ ] **Requests: ask for a cookbook to be indexed.** *Ray, 2026-11-09.*
      Anyone, signed in or not, asks for a cookbook or another source to
      be entered; contributors claim a request and queue it up; a
      claim doesn't stop it being done sooner by someone else.
      **Step 1 done (#100):** `/requests`: ask by ISBN (title and author
      from Open Library) or by title; a book already here with recipes is
      pointed to, and one already asked for gets a vote, once per account
      or per address (kept as its pseudonym). Signed out: 5 asks a day per
      address and a hidden field for bots, no email and no following
      (Ray: "rate-limited, no tracking"). Claiming is for contributors and
      up (Roles, #101). Open, claimed, done, declined with a reason;
      a claim with nothing done for 30 days reads as open again (Ray:
      "lapse after 30 days idle"). Tabs by state with counts, most wanted
      or newest, and "Yours".
      - [ ] Step 2: close a request when its book is entered by anyone
        (adding an edition with its ISBN), link a claim to the book as
        it's entered, and count work on it (a recipe added) as activity
        that keeps the claim alive.
      - [ ] The anonymous daily count is in memory, per process; move it
        to the database if there's ever more than one app process.

- [ ] **Sources, not just books.** *Ray, 2026-11-08: "a source could be a
      book or a blog or an instagram post or a tv episode or a magazine
      article".* **Step 1 done (#55):** books are sources. **Step 2, websites
      (#56):** a website is a source, one per site, optionally a
      subscription site, with recipes on its pages by address. The
      Internet Archive copy of each web page (#57). **Magazines and
      newspapers (#60):** recipes in issues, at a page. **TV shows,
      podcasts and video channels (#62):** recipes in episodes, by season
      and number, title or a video's address, at a time. **Social media
      accounts and packaging (#63):** an account's recipes are on its
      posts, by address, on any site, archived like a website's pages; a
      product's recipes are simply on its packaging, with no page.
      **Family collections (#64):** anyone signed in adds their own,
      private (only an admin can add a public one until review exists),
      after ticking that they understand what is kept and who sees it.
      Every read leaves out what the viewer can't see, including an
      ingredient or author only a private collection uses; a test asks
      every GET route as other people. Decided (Ray, 2026-11-08): privacy
      is per collection; public ones are open data like the rest.
      **Household groups (#65):** a person makes a group and invites
      others, each with a role: view, edit (also adds and changes recipes)
      or admin (also manages the group). An owner picks which of their
      groups see each private collection; joining shares nothing by itself
      (Ray, 2026-11-08). An invite link is for one person, works once and
      expires after 7 days (Ray). The larder can share the same way. Found while building family collections:
      - **A family recipe has no page**, like packaging; a church or school
        cookbook's page number could be wanted.
      - **Deleting an account** isn't built: an owner with collections is
        kept by the database (RESTRICT), and the privacy policy says
        deletion removes their collections, so the deletion has to. A
        group's last admin would leave it with none: deletion should hand
        the group to another member or delete it.
      - **Invites are links to pass on by hand**: OpenLarder sends no email,
        and keeps no address to send one to.
      - **Credits on a family collection** can't be added through any
        route yet (the book editor is an admin's, and won't open a private
        collection); "Grandma" as an author would need the same privacy.
      Found while
      building social media and packaging:
      - **Which social media pages archive at all** is still unchecked
        against the real Internet Archive: Instagram and others may save
        only a sign-in wall. The page's own link is kept either way.
      - **Packaging changes**: a recipe printed on a 2019 bag may be gone
        from the 2024 one. A product has no years or barcode (GTIN) yet;
        add them if two printings need telling apart.
      Found while building episodes:
      - [x] **Search and ingredient pages say only a page**: search says
        the issue, episode and time, or site now (#69); the ingredient page
        gets the same when it is redesigned (the API already gives it).
      - **A video's or podcast episode's address isn't archived** the way
        a web page is; whether the Internet Archive keeps video pages
        usefully needs checking first.
      - **Hosts are credited as authors**: there is no "host" role yet,
        which is a one-line change to the roles CHECK if wanted.
      Decided (Ray, 2026-11-08):
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
      person keeps lists named and arranged their own way, an item being a
      name of their own and the canonical ingredient it matches, feeding
      search. *Ray, 2026-11-10:* an item matches a specific ingredient and
      counts upward through the hierarchy (Chipotle Hot Sauce is hot sauce
      too, not the other way round); have, running low or out, no amounts;
      shared through household groups.
      - [x] Lists and search (#117): `/larder` (a Larder link when signed
        in) for lists and items, matched by name or alias to an ingredient
        you may see, or chosen, and never making a new one; have, low, out
        (out stays listed, doesn't count). Search's "Use my larder"
        (`larder=true`) counts what you have and low, each as itself and
        everything above it. Private: not history, dumps or the API's
        public reads. An ingredient merge keeps larder items.
      - [x] Sharing with household groups (#118): an owner picks which of
        their groups see each list; view members see it, edit and admin
        members change what's on it; renaming, removing and sharing stay the
        owner's. Search with your larder counts the lists shared with you.
      - [ ] A book shelf ("books I own") alongside, Phase 2.
- [ ] **LLM-assisted data processing.** *Ray, 2026-11-08.* Local models
      through n8n suggest ingredient merges, hierarchy, fixes for flagged
      lines and author names, for an admin to accept; they never write to
      the catalog. Plan and open decisions in SCOPING.md, now with the three
      n8n workflows (Ray, 2026-11-09). **Groundwork (#84):** the
      `pgvector/pgvector:pg18-trixie` image in compose and CI; migration
      0029 with `ingredient_embeddings`, `suggestions` and the public-only
      views; `scripts/n8n_role.sql`, tested. **Production (done
      2026-11-09):** OpenLarder moved off the shared `postgres:18-alpine`
      server to its own Postgres on `pgvector/pgvector:pg18-trixie` by
      `pg_dump`/`pg_restore` (an image swap would have reordered every
      app's text indexes); the `n8n_suggester` role connects over SSL on a
      port the host's `DOCKER-USER` rule opens to the n8n host only;
      Workflows 1 and 2 run. Ray: drop `openlarder` from the shared server
      once settled. **Admin Suggestions queue (#85):** `/admin/suggestions`,
      closest pairs first; Accept runs the merge (with the name to keep,
      the model's or the other) or set-parent; a suggestion naming an
      ingredient that has gone can only be dismissed, and one naming an
      ingredient the admin can't see isn't shown. **Certainty (#86):** from
      merge-v2 the model answers certain, likely or unsure in a word (a
      12B model gave 1 to nearly every number it was asked for); the page
      shows the word and puts certain first, then likely. Still to come:
      accepting line fixes, once Workflow 3 has flags to work on (open
      flags on public recipes are all no_ingredients, reference and
      duplicate-title ones as of 2026-11-09, none of them a model's job);
      the "Run now" webhook.

## Found along the way

- [x] **A line saving refuses was offered "Keep as typed"** (#78): fixed in
      #80; the check now says which lines saving refuses.
- [ ] **Splitting "A or B, or C, D, or E"**: "Lamb Shank or Shoulder, or
      Beef Shank, Shin, Cheek, or Chuck" gives an option "Beef Shank, Shin,
      Cheek," with its comma (The Heritage Cookbook). lines.py's comma rule
      only expects one "or".
- [x] **Merge two books** (#116): a moderator's "Merge into another book"
      on a book's page shows what would move, then moves its editions (buy
      links and clicks with them), recipes and their pages, credits (one per
      person and role), tags, requests and proposals to the book kept, with
      the subtitle and Open Library work it lacks, and removes the other.
      It warns of recipe titles both have. Recorded as `merge:<book>`.
      - [ ] Undo can't reverse a merge (a recipe's places move with it, by
        composite keys a row-by-row undo can't put back); it says so and
        changes nothing. A dedicated "unmerge" if it's ever needed.
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

- [x] Site design, part 5: the ingredient and author pages (#77)
- [x] Site design, part 4: a recipe's page, with where to find it, Copy
      list, and who added it (#75)
- [x] "I don't have or don't want": search leaves out recipes that need an
      ingredient you name, keeping those that offer another choice (#73)
- [x] Search ranks the recipes using the most of your ingredients first,
      then the most of the recipe you have (#76)
- [x] Search results say which of your ingredients each recipe uses, and
      what it still needs, instead of "You have all 1" (#72)
- [x] Site design, part 3: a source's page, with edition tabs and a recipe
      table to filter and sort (#70)
- [x] Site design, part 2: the search page, with a source-kind filter and
      results that say where each recipe is (#69)
- [x] Search and the ingredient picker made fast again: privacy filters
      checked by what's hidden, an index for counting, the picker counting
      only what matches, and no JIT; 3 to 6 times faster on a
      production-sized copy (#71)
- [x] An accessibility check in CI: every kind of page through axe-core's
      WCAG 2.1 AA rules in light and dark, and at phone width (#68)
- [x] A light, dark or same-as-device theme choice in the footer (#67)
- [x] Site design, part 1: the shell (colours, logo, header, footer) and
      the home page, light and dark (#66)
- [x] Household groups: invites by link, view, edit and admin roles, and
      sharing a private collection with the groups its owner picks (#65)
- [x] Family collections: anyone signed in adds their own, private, after
      a tick box; nothing private shows to anyone else on any route (#64)
- [x] Social media accounts and products' packaging as sources: posts by
      address on any site, archived; packaging recipes with no page (#63)
- [x] TV shows, podcasts and video channels as sources: recipes in
      episodes, by number, title or address, at a time (#62)
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
