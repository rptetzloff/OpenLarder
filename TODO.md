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
- [ ] **Cleanup pass.** *Decided by Ray, 2026-11-11; his spec and mockups
      are in private/ (not committed).* Eleven sections, in order, a PR
      each. Rules for all of it: real buttons, links and inputs, reachable
      and operable by keyboard with the focus ring; every control named;
      toggles `aria-pressed`, menus `aria-expanded` and `aria-controls`;
      changes without a page load said in an `aria-live` region; the
      existing colour variables only; touch targets 44px; no motion when
      the device asks for none.
      - [x] 1. Recipe page, one action bar (#149, to the spec in #150):
        under the tags, on the
        surface colour. The average as five mustard spoons, part-filled
        (4.3: four and three-tenths), with its number and count; "Rate it"
        or "Your rating" as a radio group that arrow keys move through,
        with Clear; "Want to cook" and "Cooked" as pill toggles, filled in
        the accent when pressed. Pressing the pressed one takes the recipe
        off. Under it, the shared lists it's on, and "Add to another list".
        Signed out: "Sign in to rate or save". Stacked on a phone, the two
        buttons side by side. The bar keeps its shape. The same pill toggle
        is the book page's shelf button and the Saved page's row actions.
        The spoons are 44px wide only where a finger taps (`pointer:
        coarse`), and 24px with a mouse, as the mockup draws them.
      - [x] 2. Recipe page, less boilerplate (#151): no "cookbook reference"
        paragraph; buy links as buttons after "Buy the book", the reader's
        first two with "More shops" for the rest; each ingredient a row,
        its name plain until hovered and Shop a pill at the right end
        ("Shop for almond flour" to a screen reader; with a choice, one
        pill per ingredient, named); "Cooking for a diet" a card at the
        top of the sidebar, then "On your shelf"; "Added by", History and
        Report a problem at its foot. One commission line under the
        ingredients, linking to "Buy and shop links" in the terms, with
        the grocer choice beside it.
      - [ ] The commission line, checked 2026-11-11: Amazon asks for its
        Associates statement "clearly and conspicuously" on the site, so
        the line says it whenever the page has an Amazon link, and the
        terms say it always. The FTC's guidance prefers a disclosure
        before or beside the links; this one is below the buy buttons.
        Add its placement to the lawyer review.
      - [ ] 3. Header: Requests to the footer, with two links to it where
        someone is looking for a book that isn't there (*Ray, 2026-11-11*):
        under the Sources search box, "Can't find a source? Request it",
        and on a search with no results, "Nothing matched. If the book
        isn't indexed yet, request it". "My kitchen" and the account as two
        menus; a phone menu; a skip link.
      - [ ] 4. Home: recent sources as one row that scrolls sideways, 20 of
        them, with arrows and a "Browse all sources" card.
      - [ ] 5. Search, results first: the form folded to a summary once
        there's a query, focus to the results, six diets then "Show all".
      - [ ] 6. Author names shown as "Danielle Walker", not "Walker,
        Danielle (Chef)".
      - [ ] 7. Links and buttons: terracotta underlined for links in
        sentences and a card's title; outline buttons for actions; text
        buttons only for extras; one primary and one secondary style.
      - [ ] 8. Tokens, alongside the rest: the type sizes and corner radii
        are in `:root` now (#150); fold odd sizes in and move page CSS out
        of App.vue as each page is touched.
      - [ ] 9. Home, no empty sources first: a `min_recipes` filter on the
        source list; the front page asks for recent sources with at least
        one recipe, and with fewer than six shows "Most indexed sources".
      - [ ] 10. Ingredients list, no columns of dashes: two columns,
        Ingredient and Recipes, with "Under Cheese · Also called scallion"
        beneath a name only when there's something to say.
      - [ ] 11. Home, example searches: "Try:" chips under "Cook with what
        you have", each a finished search of well-used ingredients that
        returns at least ten recipes.
- [ ] **Pages crawlers and link previews can read.** *Ray's spec,
      2026-11-11, in private/ (not committed).* Every page is the same
      empty shell until the browser fills it, so a shared link shows the
      site's card and most crawlers see nothing. The server fills the
      shell for public pages instead; the Vue app is unchanged. In order:
      - [ ] 1. A head for each recipe and source: title, description,
        canonical address, Open Graph.
      - [ ] 2. 404 for an id that isn't there; nothing of a record someone
        signed out can't see, and `noindex`.
      - [ ] 3. A plain summary in the body for recipes and sources: titles,
        pages and ingredient names only.
      - [ ] 4. `/sitemap.xml` of public records, and its line in robots.txt.
      - [ ] 5. Ingredients and authors.
      - [ ] 6. JSON-LD: Book and BreadcrumbList; never Recipe, as the page
        has no method or amounts.
      - [ ] Ray: submit the sitemap to Google Search Console and Bing
        Webmaster Tools once live.
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
      clicks. **"Get this book" (#122):** each shop a filled button, the
      format on the left (print shops first, then Kobo's ebook, unless
      you've chosen your own order) and the shop on the right. Sources
      with no cover get one drawn: the title and byline on a colour picked
      from the title (*Ray, 2026-11-10*).
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
      and Wikidata (aliases, hierarchy, then allergens). *Ray, 2026-11-11:
      "forget phases", this first, then ingredient affiliate links.* In
      three PRs:
      - [x] **The links (#133):** FDC's generic foods (Foundation, SR
        Legacy, the survey foods; 13,694, no branded products) kept in
        `fdc_foods`, loaded from its bulk download by an administrator
        (Admin › FoodData Central, or `python -m openlarder.fdc load`; the
        files are `OPENLARDER_FDC_DATASETS`). An ingredient links to one
        food and one Wikidata item, set by a moderator on its page with a
        food search; shown to everyone under "The same food elsewhere",
        with other ingredients linked to the same record as likely merges.
        A merge keeps the links. Both IDs are in the dumps (CC0).
      - [x] **Matching (#134):** Admin › Ingredient links. "Suggest
        links" (administrators) finds, for each public ingredient without
        one, the FDC food whose words are its words (likely) or one word
        more (unsure), and a Wikidata item through SR Legacy's NDB numbers
        (Wikidata's P1978; always unsure, often the plant). Moderators
        accept or dismiss each, or accept a page of likely ones at once;
        a dismissed one isn't suggested again. On the household index:
        355 likely and 74 unsure of the 1,000 most used names, 58% of
        ingredient uses likely; 940 suggestions in all.
      - [x] **Using them (#135):** from each linked Wikidata item, its
        plain English aliases and its British label (a UK name:
        "courgette") as other names, on Ingredient links' "Other names",
        one at a time; a name another ingredient has already is a merge,
        and a "subclass of" another linked ingredient's item a parent,
        both in the Suggestions queue. Lower-case names only, none naming
        the plant: Wikidata's aliases include "Allium cepa L." and "Mel".
      - [x] **Allergens (#137):** the US's nine major allergens and the
        EU's fourteen together (15; migration 0059). A moderator records,
        on an ingredient's page, that it contains, may contain or doesn't
        contain each; narrower ingredients inherit from the nearest broader
        one recording it, and "doesn't" overrides (Vegan Butter under
        Butter). A recipe's page lists what its ingredients contain or may
        contain, never what they don't, with the crowdsourced notice
        (SCOPING.md, Allergen data) on both pages. In the edit history,
        revert and the dumps; a merge keeps them, the kept ingredient's
        first.
      - [x] Suggesting allergens (#138): word rules over each public
        ingredient's name and its FoodData Central food's description
        ("butter": milk; "peanut butter", "cocoa butter", "butter beans"
        not), run by an administrator from Suggestions ("Suggest
        allergens"); each an `allergen` suggestion (migration 0060) that a
        moderator accepts or dismisses, or the likely ones shown at once.
        None for what records or inherits it already, nor below a broader
        ingredient given the same, nor again once decided. On the household
        index: 200 of the 1,000 most used names, 24% of uses.
      - [ ] Ray: build Workflow 5 in n8n (SCOPING.md) for what names
        don't say; `scripts/n8n_role.sql` now grants
        `public_allergens` and `public_ingredient_allergens`.
      - [x] Wikidata's allergen statements: checked 2026-11-11, and not
        worth suggesting from. It has no allergen property; of the 596
        foods with a USDA number, five say anything ("has effect: milk
        allergy" on milk, and the like).
      - [x] Swaps for a diet (#139): each diet avoids allergens (migration
        0061: Dairy-Free milk; Gluten-Free wheat and gluten; Egg-Free egg;
        Nut-Free tree nuts and peanuts; Soy-Free soy; Vegan milk, egg and
        seafood; Vegetarian seafood; Paleo, AIP, Low-FODMAP and the new
        Pescetarian none). *Ray, 2026-11-11:* Gluten-Free avoids every gluten
        grain, so the gluten allergen is labelled "Gluten (wheat, barley,
        rye)", and rye, barley, couscous, kamut, emmer, freekeh, triticale,
        farina and matzo are read as they should be. What each
        avoids is changed by moderators on Admin. A recipe's "Cooking for a diet"
        lists its ingredients recording one, each with the swaps recorded
        for it or a broader ingredient, for a diet avoiding all it was
        found for (a Vegan swap for butter serves Dairy-Free), whose
        stand-in doesn't record one itself. It says which allergens it
        checks, and never that the recipe suits the diet.
      - [x] Meat, poultry and pork (#143; *Ray, 2026-11-11*): three more in
        the allergen list (migration 0064), recorded, inherited, suggested
        and shown as allergens are, as "Allergens and meat". Vegan,
        Vegetarian and Pescetarian avoid all three, so their checks find
        bacon and chicken stock. The word rules read them (version
        allergen-rules-v2): on the household index, 88 more of the 1,000
        most used names get a suggestion (296 in all, 29% of uses). Run
        "Suggest allergens" again for them.
      - [x] Halal and Kosher as diets (#144; *Ray, 2026-11-11: "many
        cookbooks have it"*; migration 0065): tags for books and recipes,
        and a diet check for the part the catalog records. Halal checks
        for pork; Kosher for pork, crustaceans and molluscs; each says so,
        "and nothing else".
      - [x] Alcohol, and meat with milk (#145; *Ray, 2026-11-11: "yes to
        both"*; migration 0066). Alcohol is recorded as meat is, read from
        names by the word rules (allergen-rules-v3: "dry white wine",
        "mirin", "bourbon"; not vinegars, "root beer" or extracts), and
        Halal avoids it. A diet can avoid two things only together
        (`diet_allergens.with_allergen`): Kosher's check finds meat or
        poultry in a recipe that also records milk, across its
        ingredients, and names both sides. Fish with milk is left alone.
        The headings read "Allergens, meat and alcohol". Run "Suggest
        allergens" again for the alcohol suggestions.
      - [ ] Still unchecked: how meat was slaughtered and fish without
        scales, which nothing records. Pairs are seeded, with no form to
        change them: add one if a second diet needs it.
      - [ ] The notice's wording is in the lawyer review below.
- [x] **Ingredient affiliate links** (#136; *Ray, 2026-11-11*): a "Shop"
      link on each recipe line's ingredients and on each ingredient's page,
      to a search at a grocer: Instacart first, and each person may choose
      Amazon Fresh or Walmart instead (kept with the account, or in the
      browser), as Instacart may have nothing near them. Through
      `/go/grocer/`, counted like the book links; clicks by grocer and
      ingredient on Buy-link clicks. Each grocer shows once its setting is
      in Coolify: `OPENLARDER_INSTACART_LINK`, `OPENLARDER_WALMART_LINK`
      (deep-link templates), Amazon's existing tag.
      - [ ] Ray: join Instacart's affiliate programme (Impact), and ask
        whether a deep link to a search page earns commission.
      - [ ] Instacart's Developer Platform fills a cart with a whole
        recipe's ingredients ("Shop ingredients"), but takes no new
        applications (November 2026): apply when it reopens.
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
        Approving a book links its requests, which stay open until marked
        done (#124). Contributors change only their
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
      - [x] A report button on every public record, for anyone (#121;
        *Ray, 2026-11-10*): "Report a problem" on each recipe, source,
        ingredient and author page, with a reason and a note; signed out,
        5 a day per address and a field bots fill. Moderators fix or
        dismiss them at `/admin/reports`.
      - [x] The ingredient matching flow (#125): the recipe form already
        says what each line matches, suggests names like an unmatched
        one, and keeps one as typed as a new ingredient. The last step:
        each waiting recipe at `/admin/review` lists the ingredients no
        published recipe uses yet; approving keeps them, or a moderator
        merges one into the ingredient it's another name for (its name
        becomes an alias). A suggested change to a published recipe (#129)
        lists the ingredients applying it would add, each with the names
        most like it, so a moderator can decline one that's an existing
        ingredient written differently.
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
      - [x] Step 2 (#123): a request follows its book in, however it's
        entered (forms, import, a moderator approving it), by database
        triggers (migration 0050). Linked to a public, published source
        once that has its ISBN, or for a request with no ISBN the same
        title; shown as "it's here, being indexed". Each recipe added
        keeps a live claim alive. It stays open until someone marks it
        done (*Ray, 2026-11-10: "until marked finished"*), and asking
        for it meanwhile is a vote. A private collection never links.
      - [x] The signed-out daily counts, for requests and reports, are
        kept in the database, so a deploy or a second app process doesn't
        start them again (#131).

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
      - [x] **Deleting an account** (#140): from Your account, typing your
        display name. Goes: family collections and their history, larder
        lists, what's still waiting for review, open suggested changes,
        votes, sessions, API keys, group memberships. A group whose last
        admin it was passes to its longest-standing member, or is deleted
        if nobody's left. Stays without the name: published catalog
        entries (ODbL), requests, reports. Not the owner. The privacy
        policy says so.
      - [ ] Removing the Authgear account too, through Authgear's Admin
        API (needs an Admin API key in Coolify); until then, by email.
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
      - [x] Narrowing a big larder (#120). *Ray, 2026-11-10: "a restaurant
        sized pantry".* Search's "From my larder" section, beside "I have"
        (both count): tick lists, then only some things, or all but some
        (`larder_list`, `larder_item`, `larder_without`; `ll`, `li`, `lx` in
        the address). The larder page searches with one list, or with the
        things ticked.
      - [x] A book shelf (#141): "I have this book" on a book's page (of
        several editions, "I have this edition"), listed at `/shelf` (a
        Shelf link when signed in). A recipe's page opens at your
        edition's page, marked "(yours)"; search's "Only books on my shelf"
        (`shelf=true`; `own=1` in the address) keeps to them. Books only.
        Private like the larder (migration 0062): not history, dumps or
        the API's public reads; a book merge moves it to the book kept, an
        unmerge back with its edition; deleting the account deletes it.
      - [x] Sharing a shelf with household groups (#142; *Ray, 2026-11-11:
        "shareable exactly the same way"* as a larder list; migration
        0063): "Share" on `/shelf` picks which of your groups see it; view
        members see it there and on each book's page, edit and admin
        members put books on it and take them off. Search's "Only books on
        my shelf" counts the shelves shared with you, and a recipe opens at
        their edition when you've none of your own.
      - [x] Leaving a group, or being removed, left your larder lists
        shared with it (found in #142): they're unshared now, with the
        shelf, as family collections were.
- [x] **Saved recipes** (#146; SCOPING.md, "Saves, likes, 'want to cook'
      lists"; migration 0067). "Want to cook" on a recipe's page saves it;
      "I've cooked it" moves it to cooked; either comes off again. `/saved`
      (a Saved link when signed in) lists both, as search results are
      shown. Search's "Only recipes I've saved" (`saved=true`; `sv=1` in
      the address) keeps to them, and searches by them alone. Private like
      the larder and shelf, and shared the same way: view members of a
      group see the list, edit and admin members save to it, mark cooked
      and take off. Leaving a group unshares it; deleting the account
      deletes it; the catalog reset empties it.
      - [x] Ratings (#147; *Ray, 2026-11-11: "star ratings or similar...
        spoons or forks or salamanders"*; migration 0068): one to five
        spoons on a recipe's page from anyone signed in, changed or cleared
        at will. Everyone sees the average and how many rated it, on the
        page and in listings ("4.5 of 5 spoons"); nobody sees who. No words
        go with one, so nothing to moderate.
      - [ ] Using ratings: sorting search by them, and top-rated recipes
        on author and source pages (SCOPING.md). Not in the dumps yet.
      - [x] Notes (#148; *Ray, 2026-11-11: "more than reviews... notes....
        that are kept personal (or shared)"*; migration 0069): one note per
        person per recipe, written on its page, up to 2,000 characters.
        Yours alone unless you tick which of your groups read it, as with a
        larder list; only you change it. Saved has a Notes tab listing the
        notes you can see. No moderator or administrator role reads a note
        not shared with it; not in the history, dumps or API's public
        reads. Leaving a group unshares your notes with it.
      - [ ] Notes are free text, where the rest of OpenLarder keeps no
        amounts or method: the form asks people not to copy the recipe
        into one. Add to the lawyer review, with the terms.
      - [ ] Public written reviews: not built; Ray preferred notes.
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
- [x] **Splitting "A or B, or C, D, or E"** (#126): "Lamb Shank or
      Shoulder, or Beef Shank, Shin, Cheek, or Chuck" read "Beef Shank,
      Shin, Cheek," as one option (The Heritage Cookbook). The commas before
      each ", or" now split, not only the first; 4 lines of the household
      index read differently, all of them this shape. Existing recipes
      change when re-imported or re-saved.
- [x] **Merge two books** (#116): a moderator's "Merge into another book"
      on a book's page shows what would move, then moves its editions (buy
      links and clicks with them), recipes and their pages, credits (one per
      person and role), tags, requests and proposals to the book kept, with
      the subtitle and Open Library work it lacks, and removes the other.
      It warns of recipe titles both have. Recorded as `merge:<book>`.
      - [x] **Unmerge** (#132), for administrators, as a check on
        moderators (*Ray, 2026-11-11*). Each merge keeps a record of what
        it moved (requests, proposals and which tags aren't in the edit
        history); Admin › Merged books lists them, and Unmerge puts the
        book back under its own id with what's still with the other,
        reopening the proposals the merge declined. Anything added to the
        kept book since stays there. Refused while a recipe page joins the
        two books. Undo on a merge's change points here. Merges before
        migration 0054 have no record.
- [x] **Long-lived caching for the build's hashed files** (#130): a file
      under `/assets` with a build hash in its name is kept a year,
      immutable; its 404 is still never kept (#42), and index.html is still
      re-checked. Cloudflare respects the app's headers (Ray, 2026-11-10).

## Before launch

- [x] **Catalog reset script** (#128): `python -m openlarder.reset` in the
      app's container (README). Shows what it would delete and asks for the
      site's host name. Everything in the catalog goes, family collections
      and larder items included (*Ray, 2026-11-10*), with the catalog's
      history, flags, reports, proposals and import runs; accounts, groups,
      larder lists, requests (unlinked) and the tag list stay.
      `--everything` empties those too (*Ray, 2026-11-10*): only the tag
      list and the schema version are left, and the owner is set again by
      hand. A test fails when a new table isn't named in one of the lists.
- [x] **Backups** (*Ray, 2026-11-10*): Coolify's scheduled backups of the
      OpenLarder Postgres, daily, to a private R2 bucket of their own (never
      the public dump bucket: they hold accounts and private recipes), with
      an R2 token for that bucket only. The data dumps are no backup: public
      catalog only, and nothing restores from them.
      - [ ] A restore tested from the latest backup, before launch (not
        before the dev reset: "it's still dev data", Ray, 2026-11-10).
- [x] **Typo fixing in the importer** (#127): nothing is changed unasked
      (*Ray, 2026-11-10: "flag everything"*). At the end of each import
      run, a rare name close to a much commoner one ("Lemon Jucie", "Lemon Juice") is
      flagged on each public recipe using it, with "Change to “Lemon
      Juice”" on the flag: the line is changed and matched, the misspelt
      ingredient goes if nothing else uses it. Measured on the household
      index (typos.py): 53 names suggested, about 40 of them real typos; no
      rule was safe to apply alone (swapped letters: 9 in 10, "Crema" is not
      "Cream"). A dismissed flag stays dismissed (migration 0052). The run's
      report lists them by recipe and book.
- [ ] **#17**: sign-in and account screens that look like OpenLarder.
      Authgear's branding settings aren't thorough enough (*Ray,
      2026-11-10*). The other way is its Authentication Flow API with a
      Custom UI URI: our own pages for every step, which Authgear has to
      switch on. Next: ask Authgear whether Custom UI is on Ray's plan.
- [x] **Ray**: publish the Google sign-in consent screen (2026-11-10).
- [x] **Ray**: Cloudflare Browser Cache TTL to "Respect Existing Headers"
      (2026-11-10).

## Open decisions

- [ ] Authgear's sign-in link and code: how long they last, and whether they
      can be reused.
- [ ] Lawyer review of the privacy policy, terms, content rules, licence and
      allergen notice.
- [x] USPTO check on "Open Larder" (Classes 9 and 42): done, Ray, 2026-11-10.
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
