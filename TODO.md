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
        Report a problem at its foot. The commission is said beside the
        links it's about (Ray, 2026-11-12): a line under the buy buttons,
        and one under the ingredients for all their Shop links, with the
        grocer choice beside it; each links to "Buy and shop links" in
        the terms.
      - [ ] The commission wording, checked 2026-11-11: Amazon asks for its
        Associates statement "clearly and conspicuously" on the site, so
        the line under the buy buttons says it whenever one of the buttons
        showing is Amazon's, and the terms say it always. The FTC's
        guidance prefers a disclosure before or beside the links: the buy
        line is directly under its buttons, the Shop line under the whole
        list, not each link. Add both placements to the lawyer review.
      - [x] 3. Header (#152): Search, Sources, Ingredients and Authors.
        Requests is in the footer, with two links to it where someone is
        looking for a book that isn't there (*Ray, 2026-11-11*): under the
        Sources search box, "Can't find a source? Request it", and on a
        search with no results, "Nothing matched. If the book isn't
        indexed yet, request it". Signed in, two menus: "My kitchen"
        (Larder, Shelf, Saved, Groups) and the account under your name
        (Account, Admin for editors, Sign out). Each is a button that
        opens a list of links; Esc closes it and gives focus back, as does
        a click elsewhere or tabbing out. On a phone: the logo, Search and
        one Menu with all of it. "Skip to content" is the first thing Tab
        reaches. The header's CSS is its own (SiteHeader.vue).
      - [x] 4. Home, recent sources (#153): one row of 20 that scrolls
        sideways and snaps to cards, within the page's width; an arrow at
        each end while there's further to go (not on touch devices, nor
        when everything fits), a fade on the right while more remains, and
        a last "Browse all sources" card. Arrow keys scroll it once it has
        focus; no smooth scrolling when the device asks for none.
      - [x] 5. Search, results first (#154): arriving with a search in
        the address, the form is one line saying what was asked ("Title
        words: cake · 2 ingredients") with "Edit search"; without one, the
        form is open. After a search someone asked for (Search, or
        arriving), focus goes to the results' heading; a search that
        follows typing or a tick leaves focus alone. The count is said
        ("896 recipes"), not the whole list. Six diets, then "Show all
        diets". On a phone the filters fold behind "Filters", so the
        results come first there too.
      - [x] 6. Author names (#155): a credit kept in a catalogue's form
        ("Walker, Danielle (Chef)", "Reinhart, Peter.", "America's Test
        Kitchen (Firm)") is shown as a book would print it ("Danielle
        Walker"), wherever a source's authors are shown; what's stored is
        unchanged, and the edit form still shows it. When the author's own
        record is the same name, that's what shows, so an admin's fix on
        the author's page carries to every credit. A name already as
        printed is left alone ("Sarah Ballantyne, PhD"). It was five names
        on thirteen sources, credits from before Open Library's names were
        cleaned on the way in; authors' own records were already clean.
      - [x] And the full stop a catalogue ends a name with (#165):
        "Culinary Institute of America." and "Izabella Wentz PharmD."
        showed theirs on two sources, since the rule only looked at names
        with a comma to turn round. Found reading a live page's
        description. An abbreviation's own stays: "Inc.", "Jr.", "Ph.D.",
        and then ends the sentence it's in: "by Time Inc.", not "Inc..".
      - [ ] An author's own record is shown as stored: one typed in a
        catalogue's form ("Walker, Danielle") stays that way on the
        authors list until an admin fixes it on the author's page.
      - [x] 7. Links and buttons (#156). A link in a page is terracotta
        and underlined unless a rule says otherwise, not the other way
        round, and a card's title is too (the cover cards). An action is
        an outline button: 48 of the 80 text buttons became one, leaving
        32 for extras (Clear, Cancel, "More kinds", History, Report a
        problem), a picker's choices and the small × that removes a chip.
        A text button is the text's colour everywhere, so terracotta
        always means a link. One primary and one secondary style, on a
        `<button>` or a link that is one (`a.primary`, `a.secondary`;
        `button-primary` and `button-outline` are gone), 44px tall; in a
        table or list row `small` draws it smaller and still takes a tap
        44px high.
      - [x] The choices under a picker (#170): the ten lists that come up
        as you type to find an ingredient, a source, a recipe or an author
        were text buttons. Each choice is a row now, a real button 44px
        tall the width of its box, with its detail (how many recipes, who
        wrote it) inside it. Down from the box goes into the list, Down
        and Up move through it, Up from the first or Escape goes back, and
        taking one puts focus back in the box. One component for all ten
        (OptionList.vue). Buttons, not an ARIA listbox: Tab still reaches
        each one, as the cleanup pass's rules ask. That leaves 17 text
        buttons, of the 84 the cleanup pass set out to halve.
      - [x] The × that takes a chip, a name or a line away (#169): one
        style for all eleven (`button.remove`), drawn small and 44px
        square to tap. The square is its own box beside what it follows,
        so it lies over nothing: not a link next to it, not the text box
        below a row of chips, not the next row's × (rows of chips are 44px
        apart now). Those that were text buttons aren't, which leaves 27
        of those (32 before, counted the same way).
      - [ ] 8. Tokens, alongside the rest: the type sizes and corner radii
        are in `:root` now (#150); fold odd sizes in and move page CSS out
        of App.vue as each page is touched.
      - [x] 9. Home, no empty sources (#157): the source list takes
        `min_recipes`, counting published recipes as a card does, and the
        front page's row asks for the newest sources with at least one.
        When fewer than six have one, the row is those by how many, under
        "Most indexed sources"; still none that's empty. The Sources page
        lists everything, as before.
      - [x] 10. Ingredients list, no columns of dashes (#158): two
        columns, Ingredient and Recipes, with one muted line beneath a
        name only when there's something to say: "Under Cheese · Also
        called scallion, spring onion". The words stay in the line, so it
        reads aloud without a column's heading. Its CSS is the page's own.
      - [x] 11. Home, example searches (#159): "Try:" and four chips
        under "Cook with what you have", each a link to a finished search:
        chicken + lemon + garlic, egg + butter + flour, onion + olive oil
        + tomato, carrot + onion + celery. Measured on the live catalog,
        2026-11-12: each finds thousands, and at least twenty recipes use
        all three. A chip's name is "Search for recipes using chicken +
        lemon + garlic": the spec's wording ("chicken, lemon and garlic")
        left out the words on the chip, which the a11y check refuses
        (WCAG 2.5.3). A chip shows only when every ingredient of it is in the
        catalog, found in one request: the ingredient list takes `name`
        (exact names, as names are matched), up to twenty.
- [ ] **Round 2 fixes.** *Ray's spec, 2026-11-13, from a signed-out review
      of the live site; in private/ (not committed).* Eight sections, in
      priority order, a PR each; the cleanup pass's rules still hold.
      - [x] 1. Signing in comes back to where you were, and is counted
        (#172). Every sign-in link gives the page it's on. What's safe of
        it (a path here: one slash and no second, no backslash, "#" or
        control character, not the API or a buy link, at most 512
        characters) is kept in the sign-in cookie beside the state, never
        read back from the callback's address, and the callback goes
        there. A new account chooses its name on `/welcome` first, and
        "Continue" goes on; anyone with no name who reaches another page
        is sent there. A sign-in that doesn't work lands on
        `/sign-in-failed`, whose "Try again" keeps the page. Umami counts
        views of both, and a "sign-in" event, new or returning, that says
        no page. An invite comes back the same way, so the browser no
        longer remembers it.
      - [x] The count keeps nothing in the browser (#172; *Ray,
        2026-11-13*). The spec's one-minute cookie would have been a
        cookie for analytics, which SCOPING.md brings a consent banner
        with, so the callback marks the address it goes to
        ("#signed-in=new") and the loader takes the mark off. A link
        passed round with the mark on counts a sign-in that didn't happen.
      - [ ] The page to come back to is kept an hour, the sign-in
        cookie's life: a name chosen on `/welcome` later than that goes
        to the front page.
      - [x] Ray: after the deploy, sign in and look for the "sign-in"
        event in Umami. What the tracker sends was checked against the
        script the site loads; what Umami's collector makes of it
        couldn't be from here. *Ray, 2026-11-13: "Sign in is there".*
      - [x] 2. Title search ranked by relevance (#173). Everything with
        the words in its title is still found; the closest titles come
        first: every word a whole word of the title, plurals counting
        ("Carrot Cake" and "Crab Cakes" for "cake"), then every word
        beginning one ("Cakewalk Cookies"), then inside one ("Pancakes",
        "Cheesecake"). Within each: the title exactly as typed, then the
        rated recipes, best first, then the shorter title, then A to Z.
        With ingredients too, what you have still ranks first and this
        orders recipes level on it. "Highest rated" still puts every
        rated recipe first.
      - [ ] Words the English reading drops ("the", "and") are never
        whole words to it: a search for "the" alone has nothing in the
        first group.
      - [ ] No index was added, where the spec asked for two. The trigram
        index that finds titles is from migration 0001. A GIN index on the
        titles' English reading can't serve an ORDER BY, and went unused
        when tried. On a table of the catalog's size (18,859 titles):
        "cake" 4.7 ms ranked, 2.2 ms before; a single letter in nearly
        every title, the worst, 136 ms against 15 ms. If that matters
        one day, store the reading in a column.
      - [x] 3. Book pages on a phone (#174). Under 40rem a source's page
        runs: cover and title, Get this book, Recipes, Top rated,
        Most-used ingredients, Edition, Elsewhere. The parts are moved in
        the document itself, so Tab meets them in the order they're seen;
        wider, nothing moves. The first 30 recipes are listed, then "Show
        all N", which moves focus to the first recipe it adds; the title
        filter, the chapter and the order still work on all of them. The
        a11y check runs axe at the phone's width for this page, as it
        opens and with all shown.
      - [ ] The recipes begin 1,010px down at 375px wide on a book with six
        shops (measured on the check's 32-recipe book): a little over one
        screen, where the spec asks for about one. The "Get this book"
        box above them is 570px of it. Folding the shops behind one
        button on a phone would do it; that's Ray's to decide. *Since,
        on the live site (2026-11-13): Against All Grain's recipes begin
        684px down, on a page 5,341px tall where it was about 20,000;
        fewer shops show there. So this matters only once a book shows
        six.*
      - [x] 4. Book titles' capitals, as suggestions (#175; migration
        0071). Nothing is recapitalised when it's shown. A book's title
        with a lower-case word of four letters or more after its first
        goes to the Suggestions queue with the title-cased one ("The
        grilling book", "The Grilling Book"); small words stay small
        unless they begin the title or the part after a colon or dash,
        and a word with a capital in it is left ("BBQ", "iPad"). A title
        where an author's name has an "s" and no apostrophe before a
        capitalised word gets one with the apostrophe ("Danielle Walkers
        Healthy in a Hurry"). A moderator accepts, which changes the
        title as their edit, or dismisses, and that change isn't
        suggested for the book again. Looked at as a book is added (by
        ISBN or by hand), when a contributor's is approved, at the end of
        an import, and from "Suggest title fixes" on Suggestions
        (administrators). Only books anyone can see are read.
      - Where it leaves the spec: the lost apostrophe is a suggestion,
        not a flag (flags hang on recipes, and a suggestion carries the
        fix); books only, not every source (a website's name is often
        lower case on purpose); "with", "from" and the like stay small,
        so "Cooking with Fire" isn't offered "Cooking With Fire".
      - [x] Ray: after the deploy, press "Suggest title fixes" once, for
        the books already here. *Ray, 2026-11-13: done.*
      - [ ] What the rules can't see: a title run together
        ("Everydaycook"); a title in another language, where sentence
        case is right and the suggestion is dismissed; a possessive of a
        name that isn't an author's. Subtitles aren't read.
      - [x] 5. Tap targets on phones (#176). An ingredient's name on a
        recipe is 44px to tap, the link filling its row's height, with
        Shop its own target beside it. Under 40rem the links of "Find it
        in" and the breadcrumbs (on every page) are 44px too, drawn where
        they were: the source's link reaches up over its label, an
        author's down over the page number, a breadcrumb 12px either
        way. Measured at 390px by asking the page what a tap lands on
        through the 44px around each target: none of those is short or
        lies under another, on a book's, a website's, a show's and a
        magazine's recipe. Desktop: not a word moved.
      - What moved on a phone: a name that wraps now goes to the next
        line whole, and each line of it is 44px; a link under the
        authors (a web page's address) has a line of its own height;
        the comma after an author sits 1px further along.
      - [ ] With more authors than a line holds, a name on the first line
        is as tall to tap as its line (25px): the next line's names lie
        under the rest.
      - [ ] Other targets under 44px at 390px, found by the same measure
        and outside the spec's list: tag chips and a source's ingredient
        chips (26px); recipe titles in a source's table, in search
        results and in Top rated; authors' names on a source's page; the
        filter boxes and selects over a table; links inside a sentence
        ("Sign in to rate or save", "How this works"). 6 of a recipe
        page's 26 targets, 17 of a book page's 26.
      - [x] 6. One spelling, American, in the interface and what the
        server sends (#178; migration 0072). What a person could be shown
        in British spelling was: "Organisation" and "Organisations" on the
        Authors pages; "greyed" in the tag editor; "licence" on Open data
        and in a dump's README, with its "LICENCE" heading; "recognises"
        in the privacy policy; "organisations" in a dump's README;
        "person or organisation" in Check Open Library; "misspelt" in the
        API's documentation; and the allergen's label "Sulphites", which
        is in the database. Comments and identifiers are as they were.
        `tests/test_spelling.py` reads the pages' text and the server's
        strings for a list of British spellings.
      - The spec named "catalogue" in the interface: it's in comments
        only, nowhere a page or the API shows it (searched 2026-11-13).
      - Left, being names the API and the dumps use, not words shown: an
        author's kind is stored and sent as `organisation` (and is in
        the Authors page's address, `?kind=organisation`); the allergen's
        key is `sulphites`; a dump list's field is `licence_url`.
        Changing those changes the public API.
      - [x] "Check", not "tick", for marking a box, and dates with the
        month first (#179; *Ray, 2026-11-13: "check and November 13,
        2026"*, asked which to use). Ten places said "tick" or "ticked":
        eight on the pages, the message when a family collection's box
        isn't checked, and one route's description in the API's
        documentation. Three dates were written day first: the privacy
        policy's and the terms' "Last updated", and when History began.
        Dates the pages work out are in the reader's own language's
        order, as before. `tests/test_spelling.py` reads for both.
      - [x] 7. Covers while they load (#180). Confirmed on the live site
        first, 2026-11-13, by holding the pictures back: 76 of the first
        100 cards were empty boxes until their picture came, and a
        picture that failed left the browser's broken-picture mark. Now
        the drawn cover, title and author, is behind every picture, the
        picture fades in over it, and a failed one leaves it there. The
        first six on Sources are asked for at once; every picture has a
        width and height. The same card is on the home page's row, an
        author's page and a shelf, so those have it too.
        - The grid didn't shift before either: the card's shape was
          already set in the stylesheet. Measured, a card is 167 by 251
          with its picture held and with it shown.
        - Left as they are (*Ray, 2026-11-13: "covers are fine"*): the
          small covers beside search results and saved recipes
          (`.hit-cover`) are an empty box until the picture comes, when
          it fails, and when the book has none.
        - Not seen from here: how the fade looks on a slow phone. The
          states were checked by holding and failing the pictures in
          Chrome, not on a slow connection.
      - [x] 8. Small fixes:
        - [x] A description's ingredients add up to the recipe's lines
          (#181), the number its page gives beside "Ingredients". A line
          offering a choice was counted once for each thing it offered;
          now it is named by the first and counted once. The page's
          structured data still names everything.
        - [x] Top rated waits for three rated recipes and weighs its
          order (#181): each average as if two more people had given
          three spoons, so one person's five comes after two people's
          four and five. What's shown is still the plain average. *The
          two and the three are Claude's, 2026-11-13; the spec gives
          neither, and they're constants in routers/ratings.py.*
          - On the day it merged the live site had one rated recipe in
            any Top rated list (one person's four, in one book). That
            list goes until three of the book's recipes are rated.
          - [x] A search sorted "Highest rated" is weighed the same way
            (#183; *Ray, 2026-11-13: "Sure", asked whether it should
            be*), and so is the rating's say between two titles that
            match a search equally. There is one order in
            routers/ratings.py and all three use it. A recipe showing
            4.5 from two people can now come above one showing 5 from
            one. *Was: left on the plain average, and Ray's to decide.*
        - [x] A summary for the list pages without JavaScript, and the
          site's search action on the front page (#182). `/sources`,
          `/ingredients` and `/authors` send their first page of items
          as links, as the page first shows them to someone signed out:
          sources A to Z, ingredients the most used first, authors A to
          Z, a hundred of each, and "The first 100 of N" under a longer
          list. `/` sends what the site is, the ways in, and the newest
          twenty sources with a recipe, with `WebSite` structured data
          naming the title search.
          - Whatever is typed or chosen in the address, the summary is
            the list's first page; the browser draws what was asked for.
          - Not cached, for the reason under "Pages crawlers and link
            previews can read": a cache would keep naming a source for
            its minutes after it was made private. So each of the four
            pages now waits on its list. From here on 2026-11-13 the
            lists' API answers began in 0.21 to 0.23 s (sources), 0.29
            to 0.31 s (authors) and 0.32 to 0.37 s (ingredients),
            against 0.10 to 0.16 s for `/healthz`: the pages begin about
            0.1 to 0.2 s later than they did.
          - The pages themselves, once it was live (seven or eight
            requests each, from here, 2026-11-13): `/sources` began in
            0.17 to 0.22 s, `/` in 0.20 to 0.24 s and once 0.39 s,
            `/authors` in 0.27 to 0.31 s and `/ingredients` in 0.27 to
            0.37 s, against 0.11 to 0.16 s for `/privacy`, which asks
            the database nothing.
          - If the database can't be asked, the page is sent without
            its summary, as before this, not as a 500.
          - Not checked: whether a search engine uses the summary.
            Google stopped showing a search box under a site's result
            on 2024-11-21 (its Search Central blog, 2024-10-21, read
            2026-11-13), so the search action gets none from it; the
            same post says the markup needn't be removed and that
            `WebSite` is still read for the site's name. It is what the
            spec asks for.
      - The two commission lines on a recipe's page stay as they are,
        each beside the links it covers (*Ray, 2026-11-13*).
      - Still to review, from the spec: the signed-in pages, and a
        keyboard and screen reader pass over the action bar, the menus
        and the home page's scrolling row.
- [ ] **Round 4.** *Ray's spec and wireframes, 2026-11-14, measured on a
      local build of `dev` at 360, 384, 412 and 1280px, signed in as an
      owner; in private/ (not committed). It takes in round 3's two
      features as its parts D and E.* A PR for each line, in this order;
      the cleanup pass's rules still hold.
      - [x] A. Sideways overflow on phones (#184).
        - A1. A recipe's page, signed in, was 24px too wide at 384px and
          48px at 360px, with "Cooked" cut off. Measured here the same,
          and only on a touch screen: the five spoons of "Your rating" are
          44px each under a finger, and in a row with their label and
          Clear they were 367px, which the save buttons under them were
          then stretched to. So the label has a line of its own on a
          phone, Clear goes under the spoons where even that is too wide
          (320px), and the two buttons share a row while their labels fit
          and take one each when they don't. The spec named the buttons'
          row as the cause; it was what showed.
        - A2. A word may break anywhere, said once for the page, the admin
          bar and the footer, where six rules in App.vue and seven in
          components had each covered one place. A title, a note or a web
          address of one long word no longer widens a page.
        - What that costs, and what was done about it: a table no longer
          keeps a column as wide as its longest word, and a row no longer
          holds a heading at its width, so something squeezed breaks its
          words where it used to run over. Found by looking for them: the
          authors' list broke "Sources" and "Recipes" beside a long name
          (1280px), a larder list's name broke beside its buttons
          ("Pantry", 360px), and a moderator's allergen form had
          "Inherited" in three lines of three letters. A column's heading
          and a number now stay whole everywhere; the list's buttons go
          under its name; the form is a row for each allergen on a phone.
        - A3. Ingredient links already became a card for each row on a
          phone, by the rule every such table shares; it was seen for the
          first time with rows in it (the check plants three foods and
          four suggestions), and its two buttons may now wrap. Of the two
          components the spec names beside it, the allergen form had the
          table, above; "The same food elsewhere" has none, and its "View"
          links keep their width beside a long description.
        - A4. The accessibility check looks at every page on a 360px touch
          screen, where it was 390px with a mouse, with a word of sixty
          letters as a book's title, its author, a recipe's title (twice,
          so both are flagged), an ingredient, a larder item, a request,
          and in a note and a report beside a web address as long. Before
          the fixes it failed 88 of 400 page views. It also fails a page
          that breaks a word of up to twenty-five letters in two, and its
          control must catch one of each. In `web/a11y/check.mjs`, not a
          Playwright test as the spec says (*Claude's choice*): it already
          loads every page as each kind of person, and Playwright would be
          a dependency for what it does without one.
        - [ ] A display name can't be sixty letters: thirty-two is the
          most one may be (names.py), and the check's cook has one of
          those.
        - [x] (#197, round 5's item 2.) The check looks at two widths.
          Between a phone and a
          desktop the header doesn't fit when signed in: with a nine-letter
          name, a page is 78px too wide at 650px and 28px at 700px, and
          fits at 740px; with a thirty-two-letter one, 176px too wide at
          768px and 44px at 900px. The sections, "My kitchen" and the name
          are one row that can't wrap. Measured 2026-11-14 on the build
          before this; not changed here.
        - [ ] Words on a drawn cover aren't looked at for breaking: its
          title is fitted to the cover and may break by design.
      - [x] B1 to B3. What every admin page spends before its first thing
        to act on, on a phone (#185). The aim, for all of part B: that
        thing starts within 450px of the top at 384 x 832.
        - B1. The admin bar is one row on a phone, 49px where its thirteen
          links took five rows and 157px: "Admin", and a button with the
          page's name that opens the links two to a row, each 44px to
          tap. Esc closes it and gives the button the focus back. On
          Sources, which carries the bar and isn't one of its pages, the
          button says "Admin pages" (*Claude's choice*). Above 40rem
          nothing changed.
        - B2. One sentence under each admin page's heading, and the rest
          under "How this works", closed, after the page's controls:
          eleven pages, Your flags among them. Nothing was dropped. Three
          things the spec doesn't say (*Claude's choices*): People has no
          sentence under its heading, since its paragraph's first is four
          lines on a phone and says nothing the heading doesn't; Bulk
          import keeps its link to the history up there; and where a page
          has no controls (Review, Merged books) it follows the heading.
        - B3. Under 40rem a wide page's padding is 1rem, a breadcrumb's
          and a list page's heading's bottom margins are halved, a
          section's title has 1.5rem above it and a panel 0.75rem and 1rem
          inside. That's every wide page, not only Admin's.
        - Measured on the check's own data, the development banner taken
          off, before and after: Admin 389 to 265px, Merged books 502 to
          318, Bulk import 521 to 356, Reports 548 to 389, Recent changes
          557 to 398, People 764 to 407, API usage 681 to 432, Flagged
          recipes 567 to 433.
        - [ ] Four are still past 450px: Review 469 (was 623), Buy-link
          clicks 483 (591), Suggestions 566 (1,063) and Ingredient links
          624 (908). Clicks is B8's. What's left on Suggestions and
          Ingredient links is their filter buttons, three rows of them:
          B5 and B6 turn Flagged recipes' and People's into one choice
          on a phone, and the same would do here, which the spec doesn't
          ask for. Review's is its "Suggested changes" heading.
        - [ ] "How this works" costs a row of 44px where it's closed, so
          a page whose introduction was short gains little from B2 alone:
          Flagged recipes' went from four lines to two and that row.
        - Found on the way: Admin and Buy-link clicks were 24px too wide
          at 320px, where a panel's column couldn't be narrower than
          20rem. It can now. The check's phone is 360px, so it didn't see
          it, and still wouldn't.
        - The check presses the bar's button on a phone and opens a "How
          this works", and fails if the bar is taller than a row there or
          its links aren't in the bar on a wide screen.
      - [x] C. A simpler search page (#188), laid out from the two
        wireframes. On a 384px phone the form is 241px before a search
        where it was about 1,000px, and after a title search the first
        recipe starts 400px down.
        - One bar that stays: the title words and Search. The heading is
          still there for whoever goes by headings, not drawn. The form
          no longer folds to a line with "Edit search".
        - "Cook with what you have" under it, with "Use my larder" beside
          it for someone who has one: it ticks every list, or the ones
          ticked before it was last unticked.
        - "Show", when there are ingredients or a larder: anything using
          them (as before), missing 2 or fewer, or only what can be made
          now. `missing_max` in the API (0, 1 or 2), `missing` in the
          address. What counts as missing didn't change. Kept to it, a
          recipe says "You have everything" or "Missing: …", the count
          says "you can make now", and an empty list offers the next
          step as a button.
        - "More options (n)": what to leave out, which sources, only my
          shelf, only saved, and which larder lists with the rest of the
          larder's picker. Closed until wanted, open for a link that uses
          one, and n is how many are in use.
        - What's narrowing the results is a row of chips over them, each
          a button that takes itself off, with "Clear all": the Show
          choice, tags, kinds of source, my shelf, saved, what's left
          out and which sources. Focus goes to the next chip, or the
          count.
        - "Copy link" is beside the count.
        - Beside the results Diet and Course are open, and Source kind and
          Cuisine and technique closed unless something in them is ticked.
          On a phone they're under "Filters (n)", beside the order.
        - Every link made before opens the same search: tried with
          `larder=1`, `own`, `sv`, `kind`, `x`, `sort` and `page`, and the
          check now holds one of them to it.
        - Where this leaves the spec (*Claude's choices*): the count and
          its controls come before the filters for a keyboard, so that a
          phone reads count, then Filters and the order, then recipes, as
          the wireframe has it; how the ingredient box works ("cheese
          finds cheddar") shows while the box is in use, and is said to a
          screen reader always; a link's `missing=1` is offered as a
          choice only while it's the one chosen; and with the list kept
          to what can be made, "Uses your …" isn't said, as in the
          wireframe.
        - [ ] The spec's "about 300px" to the first recipe after a search
          is 400px for a title alone, and 591px with two ingredients, the
          Show choice and a chip. What's between is all in the wireframe.
        - [ ] A link for a filter opens "More options" as the spec asks,
          which on a phone puts the recipes a screen further down for
          whoever follows one.
      - [x] B4 to B12. Page by page, on a phone (#189). Measured at 384px
        on the check's data, the development banner taken off; a wide
        screen is as it was unless said.
        - B4. Admin is a row for each tool, its name at the left and what's
          waiting at the right, those with something waiting first, and
          only they say what they're for (one line of it on a phone). A
          row is 70px where a card was 140px. Drawn once the counts are
          in, so the rows don't change places. A grid on a wide screen.
        - B5. A flag is the recipe with Fixed and Dismiss beside it, then
          one line of why and which book, then its detail: 103px where
          it was 159px. A row with more to it (a change offered, a reason
          being typed, what was decided) has that under the rest.
          Twenty-five at a time, in the API too (it was fifty). The
          reasons are one select. Your flags is the same page.
        - B6. A person is their name and role, then one line of the rest
          ("Trust: waits for review · 0 claims · joined Nov 14, 2026")
          with Trust and Withhold at its end where they apply: 70px with
          buttons, 48px without, where it was 153px. The roles are one
          select.
        - B7. A change of more than five rows is one line ("added 128
          recipes, 96 ingredient lines") with the rows behind "Show
          details", on every width and in a record's own history too.
          Recent changes on the check's data went from 7,336px to
          4,486px.
        - B8. On Buy-link clicks and API usage a record's numbers are two
          to a row, each with its label at the left and the number at
          the right; a record with one number has it beside its name.
        - B9. On Sources the four ways to add one are behind "Add a
          source": the first cover starts at 682px where it was 815px.
          Someone with only the one way sees it as it was.
        - B10. On an ingredient's page three cards saying there's nothing
          are one line saying so; the allergens' notice is under "How
          this works" while nothing is recorded; and a recipe using it is
          its title, then one line of which book and where: 95px where
          it was 173px. The first recipe starts at 866px where it was
          1,006px.
        - B11. Bulk entry's instructions are under "Keys and shortcuts",
          its status is a line, and a row has the page and chapter on one
          line, then the title, then the ingredients. The first row
          starts at 523px where it was 626px.
        - B12. On a book's page "I have this book" and "Search in this
          book" are side by side, the rest behind "More", and the title
          has the page's width: a long one is three lines where it was
          seven. The first recipe starts at 1,320px where it was 1,411px.
        - Not asked for, and done with them (*Claude's choice*, said in
          #185): the kinds on Suggestions and the tabs on Ingredient
          links are one select on a phone too. The first thing to act on
          went from 566px to 501px and from 624px to 516px.
        - Where this leaves the spec, each *Claude's choice*:
          - B10's notice is folded away only while nothing is recorded.
            Beside allergens it's what qualifies them, and stays in view.
          - B10 drops "the repeated ingredient name" under a recipe where
            the book's line is the ingredient's name, and keeps a line
            that says something else.
          - B12 puts the title above the cover and what's beside it, not
            below: it's the page's heading.
          - B12's "More" is on a phone only; on a wide screen what it
            holds is in a row, now with "Edit tags" in it.
          - B4's Import history shows how many imports there have been,
            and doesn't count as something waiting.
        - [ ] Still past the 450px aim at 384px: Buy-link clicks 483,
          Review 469, Suggestions 501, Ingredient links 516, bulk entry
          523, Sources 682 for a moderator, an ingredient's page 866 and
          a book's page 1,320 to their first recipe. The spec's fixes for
          each are all in; what's left is the pages' own headings, their
          "How this works" row and the buttons that belong above a list.
        - [ ] B11's row reads page, chapter, title on a phone, and a
          keyboard still goes page, title, chapter, as on a wide screen
          where the title is over the chapter.
        - [ ] Where one of an ingredient's three cards has something, the
          other two still say they have nothing: the spec folds them only
          when all three are empty.
      - [x] D1. Shops in a table of their own (#190), with no visible
        change. Migration 0073 makes `shops` with a row for each of the
        six booksellers and three grocers, each one's setting copied from
        the variable it was in and the shop switched on where that was
        set. buying.py and grocery.py read the rows (shops.py), kept a
        minute in the process. Its own PR, ahead of `/admin/shops`
        (*Claude's choice*: the spec has them on one line), so the move
        could be seen to change nothing before anything is built on it.
        - That nothing changed: on one database, the build before and
          this one gave the same buy list for every edition and the same
          address from every `/go/` link, all nine shops, 54 of 54; and
          so did this build started with none of the variables set.
        - A key is unique among its kind, not among all shops as the spec
          has it: Amazon and Amazon Fresh are both `amazon`, at
          `/go/amazon/…` and `/go/grocer/amazon/…`, and both are on the
          web already.
        - `{words}` (a book's title and author, for a search) is a
          placeholder the spec doesn't list: Kobo is searched that way,
          and with it Kobo's address is in its row like the others'.
          Amazon's is still made in code, as the spec says.
        - For one release a row nobody has changed that has no setting
          still takes it from its variable, with a warning in the log
          naming it. D3 takes that out with the variables.
        - A reset keeps the shops, of the catalog or of everything
          (reset.py): they're the site's configuration. With
          `--everything`, who last changed one goes with the accounts.
          The reset's own test, that every table is named as emptied or
          kept, is what asked.
        - [ ] Ray: nothing to do in Coolify for this. After it's deployed,
          the log should have no line saying a shop "has no setting in
          the shops table"; one would mean a variable the migration didn't
          see.
      - [x] D2. `/admin/shops`, for administrators (#191): Shops, linked
        from the admin bar and Admin, for an administrator and not a
        moderator, the page and its API both.
        - Booksellers and Grocers, each in the order shown. A shop has an
          "On" tick, "Move up" and "Move down", and "Edit"; its name and
          key, what it earns, its clicks in 30 days, and when it was last
          changed and by whom.
        - The form's fields follow how the shop's address is made. What
          couldn't work is refused in words: an id that isn't a number
          for Bookshop.org, a tag that isn't an Associates tag, an address
          or deep link not starting https://, a deep link without {url},
          a placeholder the kind of shop hasn't. A shop switched on must
          have what its address needs.
        - "Test link" shows where a click would go for a sample book or
          ingredient, its host marked, with nothing saved or counted.
        - "Add a bookseller" and "Add a grocer": a key is for good, and
          unique among its kind.
        - A shop with clicks recorded has no "Delete…"; one without does.
        - A change is on the site at once for the process that made it
          and within a minute for the others. It's in Recent changes
          (migration 0074), where only an administrator can undo it:
          undoing a shop's change is changing a shop.
        - By keyboard: moving a shop keeps focus on its button, or on its
          other one at an end; a form that closes gives focus back to
          the button that opened it; and each change is said ("Kobo moved
          up: now 5 of 6.").
        - For the release the variables are still read: a shop whose
          setting is in one says which, and switching it on or off, or
          saving it, puts the setting on the shop.
        - [ ] Producers aren't on the page: D4.
        - [ ] `OPENLARDER_META_TAGS` (site verification for affiliate
          programmes) could move here later; the spec leaves it out.
      - [x] E. Google Ads sign-up tracking with none of Google's script
        (#192): built, and off unless `OPENLARDER_AD_CLICKS` is set.
        - An ad's click id (`gclid`, `gbraid`, `wbraid`) on a page's
          address goes into the signed cookie `ol_ad_click` for 90 days.
          Not for Do Not Track or Global Privacy Control, the EEA, the UK
          or Switzerland, or someone signed in.
        - A new account in that time adds one row to `ad_conversions`
          (migration 0075), in the sign-in's transaction: no user column,
          and the sign-up's time to the minute, so not the account's own
          to the microsecond. A returning account adds none. Any sign-in
          clears the cookie.
        - Rows go after 90 days; they're in no data dump and no edit
          history; `reset --everything` empties them.
        - `scripts/ads_role.sql` makes the `ads_exporter` role, which may
          read the table and mark a row exported and nothing else;
          `scripts/ads_export.sql` has the export's two statements. Both
          are tested as that role.
        - The privacy page has the section, the cookie and two changed
          sentences, shown only while it's on. README.md has the set-up.
        - Claude's choices, to overrule if wrong: no country header, no
          cookie; the rules asked again at sign-up; the time to the
          minute, rounded up; the privacy wording shown with the switch
          and not ahead of it; in the page's voice ("OpenLarder", not
          "we").
        - [ ] Ray: have the privacy wording checked before switching it
          on, with the lawyer review already planned. With it on, the
          page stops saying OpenLarder doesn't "share" personal
          information, and says what it tells Google.
        - [ ] Ray: Cloudflare's IP Geolocation on (without the country
          header nothing is kept); Google Ads auto-tagging and the
          conversion action; the role, the sheet and the n8n workflow;
          then the setting. README.md, "Sign-ups from ads".
        - [ ] Not checked from here: the n8n workflow, and whether Google
          takes a row. One real ad click and a new account shows both.
        - [ ] The accessibility check now looks at the privacy page with
          ad clicks on, the longer of its two; the shorter isn't looked
          at any more.
        - [ ] Later, each its own decision: buy-link clicks as a second
          conversion (changes what the privacy page says of them);
          Microsoft Ads' `msclkid`; a direct push to Google's Data
          Manager API in place of the sheet.
      - [x] D3. The affiliate environment variables go, a release after
        D1 (#193): the eight settings and their validators are out of
        `config.py`, and nothing reads the variables but two migrations.
        - Migration 0076 first makes standing what the app did for that
          release: a shop nobody has changed, with no setting, takes its
          variable's and is switched on. So no link changes, whether or
          not the setting was moved by hand. It writes no edit history.
        - The admin page no longer says "its setting is still in …", and
          switching a shop no longer copies anything.
        - A variable left behind does nothing, and one of the wrong shape
          no longer stops the app starting.
        - The accessibility job and a new database still seed their shops
          from the variables, in migrations 0073 and 0076, which read the
          environment themselves.
        - [ ] Ray: once this is deployed, the eight variables in Coolify
          can be deleted (`OPENLARDER_BOOKSHOP_AFFILIATE_ID`,
          `_AMAZON_TAG`, `_BARNES_NOBLE_LINK`, `_THRIFTBOOKS_LINK`,
          `_BOOKOUTLET_LINK`, `_KOBO_LINK`, `_INSTACART_LINK`,
          `_WALMART_LINK`). Not before: 0076 reads them as it deploys.
      - [x] D4. Producers, as a kind of shop (#194): built, and none
        added. A producer is a farm, a mill or a maker that sells
        ingredients itself.
        - An administrator adds one on Shops, under Producers: its name,
          its referral link (used as written), what it is, its offer, the
          states it ships to, the ingredients it supplies, what a click
          earns, and what's said beside its link. Switched on, it must
          say what is earned and by whom, unless a click earns nothing,
          which the site then says itself.
        - `/producers` has a card for each, in the administrator's order.
          The footer links it once one is switched on, and the privacy
          page and the terms speak of producers only then.
        - An ingredient's page has "From a producer" under its recipes'
          heading: those that supply it or a broader ingredient it's
          under (migration 0077, `producer_ingredients`), two at most.
          Not on recipe pages, and the Shop button is still a grocer's.
        - A click goes through `/go/producer/<key>` and is counted in
          `producer_clicks`: which producer, which page, when, nothing
          about who, and nothing for a bot. They're on the Shops list and
          on Buy-link clicks.
        - What a producer supplies is in the edit history, and only an
          administrator can undo it. Merging an ingredient keeps its
          producers. Neither table is in a data dump.
        - Where it ships is said; nobody's place is guessed.
        - Claude's choices, to overrule if wrong: a producer can only be
          given ingredients everyone can see, never one that only a
          private family collection uses; the footer link and the two
          pages' paragraphs wait for the first producer; the link reads
          "Visit" and the producer's name, so two on a page differ; an
          ingredient's page shows one line of the description, with the
          offer and where it ships on one line, so two cards cost less
          of a phone's screen.
        - [ ] Ray: the first producer isn't added. When it has said its
          link may be posted publicly, add it on Shops (Add a producer),
          with its disclosure, and switch it on.
        - [ ] Later, if wanted: show a producer only where it ships.
          Cloudflare's header for the visitor's region would do it, once
          it's confirmed on the plan.
        - [ ] Above an ingredient's recipes on a 384px phone, one
          producer's card is about 230px and two about 540px with their
          heading (measured): the list starts that much lower. Ray's spec
          puts them there; after the list is the other place for them.
- [ ] **Round 5.** *Ray's spec and wireframes, 2026-11-15, from a review
      of `dev` at be914e9 (the build with "Want this book"): a local copy
      with test data, signed in as an owner and signed out, at 360, 384,
      412 and 1280px, then every 20px from 640 to 1100px; in private/ (not
      committed).* A PR for each item, in this order.
      - [x] 1. The ingredient hierarchy in plain words (#196). *Ray,
        2026-11-15: "Counts as".* Cheddar counts as cheese, and cheese
        includes cheddar, where the site had said it as a place: comes
        under, under it, broader, narrower, top level. "Counts as" holds
        for kinds, parts and cuts, which "a kind of" doesn't. An
        ingredient that counts as nothing is a main ingredient ("Main
        ingredients only" on the list). Changed wherever a person reads
        it: an ingredient's page and its moderator's form, the list,
        Search's hint, the front page, allergens, suggestions, a
        producer's form, Ingredient links, the pages crawlers and link
        previews read, the data dictionary (which now says the column is
        `parent_id`), and the two refusals. On an ingredient's page a
        "Counts as" or "Includes" card with nothing to say isn't there.
        Only words: no column, API field, parameter or address changed,
        and comments and docstrings keep the old words until the code
        around them is touched. `tests/test_counts_as.py` fails if the old
        words come back where a person reads them.
        - Beyond the list's table, the same words in four places it
          didn't name (Claude's choice, 2026-11-15): the admin bar's "Put
          under…" is "Count it as…"; the moderator's form says "Counts as
          “Ginger”" where it said "Under “Ginger”"; a suggestion reads
          "A counts as B" and its refusal "which counts as which"; and an
          ingredient's history says "counts as: nothing → “Cheese”" where
          it said "parent".
        - Found by looking at the list, and fixed: its count read "10
          ingredientsmatch “cheddar”", the space lost with a template
          that held the last part. It was on openlarder.com. The
          accessibility check reads the sentence now.
        - The list's own check (a grep that should print nothing) prints
          seven lines, all in docstrings, which the list also says to
          leave: allergen_rules.py, models/allergens.py (two),
          models/shops.py, routers/suggestions.py and wikidata_names.py
          (two). The test reads Python's strings apart from its
          docstrings, so it holds the rule the grep was after.
      - [x] 2. Between a phone and a desktop, 640 to 1100px (#197).
        - 2a. The recipes using an ingredient: each column has its share
          (the recipe 43%, the book 29%, where it is 7.5rem, the line as
          written the rest), and up to 56rem it's the phone's cards. The
          book's column had 71px of an 820px screen. The list said 5.5rem
          for "Where"; with its padding off that is 64px, and "p. 22 ·
          4.5 of 5 spoons" was four lines of it, which the list's own
          rule for tables (2e) fails. So 7.5rem, and the percentages give
          up the difference (Claude's choice, 2026-11-15).
        - 2b. Flagged recipes and My flagged recipes are cards up to
          60rem.
        - 2c. Buy-link clicks is cards up to 56rem, an ISBN stays whole,
          and a title or an address in its first column may wrap. So is
          API usage, which is the same kind of table and takes the same
          rules.
        - 2d. The header is the phone's (logo, Search, Menu) up to 56rem,
          and the account button shows about twelve letters of a name,
          with an ellipsis. The button is still called by the whole name,
          and a name that's cut is said in full at the top of its menu.
          Twelve by width (12ch), not by count, so nothing but how it's
          drawn changes.
        - 2e. The check looks at every page's layout again, signed in, at
          700, 820, 900 and 1024px, and at every width fails a table's
          cell under 6rem wide with more than three lines in it. On the
          layout before this it failed 159 views. It is 916 views where it
          was 524, and 80 seconds here where it was 47.
        - 900px isn't in the list. A sweep of every 20px from 640 to
          1100px (`A11Y_BETWEEN`), after the list's three widths passed,
          found seven views on three pages that didn't, six of them from
          900px to 960px, just past 56rem. So the check has that step too.
        - Found by the check at those widths, and fixed, beyond the list:
          People at 700px (a column 71px wide, ten lines deep; cards up to
          56rem now); the Authors list at 700px (72px too wide with a long
          name kept on one line; its columns have shares); a group's
          members beside the invite panel at 900px and 1024px ("Remove"
          one letter to a line; one column up to 64rem, and the name may
          wrap); Merged books at 660px ("Into" in 92px; cards up to
          56rem); a shop's key after a long name (broken mid-word; a box
          of its own).
        - The sweep's limits: the check's own planted data, in the light
          theme, signed in. After the fixes it was 2,820 views, none with
          a problem. It says nothing of pages with real rows, which is
          where the list found the first of these.
      - [x] 3. Search results, Saved recipes and Notes have a block of
        the source's cover color beside a recipe where there's no picture,
        not an empty white box (#198). The same color its drawn cover has
        everywhere else, with no words on it: the title is beside it. The
        block is also what shows until a picture arrives, and when one
        fails, where the browser's broken picture was. The check plants a
        recipe in each of its two books with pictures and looks at both
        thumbnails.
      - [x] 4. Breadcrumbs stop at the parent, since the last one repeated
        the title under it (#199). "Sources / Fiery Ferments" above a
        recipe, "Sources / Books" above a book, "Ingredients" above an
        ingredient, "Admin" above an admin page: all twenty pages that
        have one, through one component (Crumbs.vue). On a phone it is one
        link back to the parent, with a chevron, on one line with an
        ellipsis, and 44px to tap. On a recipe's page on openlarder.com at
        384px the trail was 135px tall and the title began 224px down.
        - "Books" in "Sources / Books" is a link now, to the sources of
          that kind, so a phone has "‹ Books" above a book and not
          "‹ Sources" (Claude's choice, 2026-11-15, said to Ray before it
          was built).
        - Search engines are still given the whole trail, the page itself
          last (pages.py: the BreadcrumbList). The page crawlers read
          stops at the parent, as the page does.
      - [ ] 5. A page's own admin bar (ingredient, source, author) is one
        row on a phone, as the main one is.
      - [ ] 6. Saved recipes: one button for each tab ("Cooked it", "Cook
        again") and Remove, each with an Undo. *Ray, 2026-11-15: one
        button per tab over the two pills.*
      - [ ] 7. A book's buy buttons are grouped by format under a heading
        and say only the shop, in the recipe page's outline style: "Print"
        on a button read as printing the page.
      - [ ] 8. Your shelf, Your larder and Saved recipes keep one sentence
        under the heading and fold the rest into "How this works", open
        only when the page is empty; Your account says when the agreement
        was accepted and folds its text.
      - [ ] 9. Search on a phone: the filters go inside "More options".
        *Ray, 2026-11-15: "Filters probably makes sense under More
        options".*
      - Not checked by the review, so still open: a keyboard-only and
        screen reader pass (open since round 2); signed-in pages on
        openlarder.com itself; the review queue, Ingredient links and
        Merged books with real rows; the dark theme.
- [ ] **Pages crawlers and link previews can read.** *Ray's spec,
      2026-11-11, in private/ (not committed).* Every page is the same
      empty shell until the browser fills it, so a shared link shows the
      site's card and most crawlers see nothing. The server fills the
      shell for public pages instead; the Vue app is unchanged. In order:
      - [x] 1. A head for each recipe and source (#160): the page's own
        title, a description under 160 characters ("Banana Bread is on
        page 190 of Against All Grain by Danielle Walker. Ingredients:
        Egg, Almond Flour, and 6 more."), its canonical address and Open
        Graph tags, in place of index.html's. Built from the API's own
        answer for someone signed out, whoever asks, so it can't say more
        than the API would to a stranger (pages.py).
      - [x] 2. What isn't there, and what isn't for everyone (#160): 404
        for an id that names nothing; for a private record or one waiting
        for review, the plain page with `noindex` and nothing of it, its
        owner included (their browser fills it in); 301 from a merged
        source to the one kept. The search page is `noindex, follow`;
        saved, shelf, larder, groups, account, admin and requests are
        `noindex`. The privacy sweep asks the filled pages too.
      - [ ] The card image is the site's on every page: no cover is
        OpenLarder's own (they're fetched from Open Library as asked
        for), and the spec says a cover only when it is.
      - [ ] Nothing is cached yet: a filled page asks the database what
        the API then asks again for the browser. The spec's few minutes'
        cache would also keep showing a record for those minutes after
        it's made private; measure before adding one, and drop the entry
        on that change if so.
      - [x] 3. A plain summary in the body for recipes and sources (#161),
        where the SPA mounts and so replaced when it does. A recipe: its
        name, its source and who made it as links, the page (or the issue,
        the episode, the web address), and each ingredient as the source
        names it, linked. A source: what it is, who made it, its editions,
        and its recipes as links with their pages, the first 500 and then
        "All N recipes". Nothing the page doesn't show anyone; nothing at
        all for a record that isn't everyone's.
      - [ ] The summary shows for a moment before the SPA draws the page
        over it (the spec says leave it visible). If it's noticed, hide
        it as `.visually-hidden` is, once Google is seen to read it still.
      - [x] 4. The sitemap (#162): `/sitemap.xml` is an index of
        `/sitemaps/<kind>-<n>.xml` for recipes, sources, ingredients and
        authors, at most 50,000 addresses a file, each with the day its
        record last changed. Only what someone signed out can see, whoever
        asks. robots.txt points at it.
      - [x] 5. Ingredients and authors (#163): the same head and summary
        for an ingredient's page (what it comes under, its other names,
        what's under it, and the first 100 recipes that use it) and an
        author's (their sources, and who they're credited with). One only
        a private recipe or collection names is as hidden as it is. The
        front page and the Sources, Ingredients and Authors lists say
        which address is theirs (the one without a query), and the lists
        have their own title and description.
      - [x] A merged ingredient's or author's old address goes to the one
        kept (#171; migration 0070): each merge records the id that went
        and the one kept, and the old page answers 301 to where it is
        now, following merges on, if anyone can see it. Merges made
        before this have no record, so their old addresses are still 404.
      - [x] 6. Structured data (#164), one JSON-LD block a page. A source
        is a Book with who wrote it (a Person, or an Organization for a
        test kitchen), its ISBN and its year; or a WebSite, a Periodical,
        a TVSeries, by its kind. A recipe's page is a WebPage, part of its
        source and about its ingredients: never a Recipe, as the page has
        no method or amounts. An author is a Person or an Organization,
        with the same one on Wikidata and Open Library. Every page has
        its breadcrumb. None for a record that isn't everyone's.
      - [ ] Ray: run a recipe's page and a book's through Google's Rich
        Results Test once live (the spec's check: valid Book and
        BreadcrumbList, no Recipe).
      - [ ] Ray: submit the sitemap to Google Search Console and Bing
        Webmaster Tools once live.
- [x] **Authors sorted by last name** (#167). *Ray, 2026-11-12: "we need
      to also be able to sort authors by last name".* The Authors list's
      Sort has "Last name, A to Z" beside "Name, A to Z" and "Most
      recipes": a person is filed by their last name ("Yotam Ottolenghi"
      under O), an organisation by its name less a leading "The". Letters
      after a name aren't the last name ("Sarah Ballantyne, PhD"); a
      particle with a capital begins it ("Van Damme" under V), in lower
      case it doesn't ("de la Renta" under R). The names read as before.
      - [ ] It can't tell a last name of two words from a middle name:
        "Mónica Fernández Perea" is filed under Perea. A name to file an
        author by, set by hand, would fix those.
      - [ ] The names still read first name first when filed by last name;
        "Ottolenghi, Yotam" in that order may be easier to scan.
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
      (Ray, 2026-11-09: no account yet). *Superseded (#193): every setting
      named in this item is on its shop now, at `/admin/shops`, and the
      variables aren't read.* **More shops (#95):** Barnes &
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
      (deep-link templates), Amazon's existing tag. *Superseded (#193):
      each grocer's setting is on its shop now, at `/admin/shops`.*
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

- [x] **"Want this book"** (#195). *Ray, 2026-11-14: "Add want this
      book to to-do", after asking when it had been removed.* It never was
      there: nothing in the code or its history had it. What there was
      beside it: "I have this book" on a book's page, which puts it on
      your shelf and had the one state; "Want to cook" and "Cooked" on a
      recipe; and "Request it" on Sources, for a book to be indexed.
      *Ray's answers, the same day, to what Claude asked:*
      - It's a second state of the shelf, beside having the book ("Second
        shelf state"): a book on your shelf is one you have or one you
        want.
      - Search's "Only books on my shelf" leaves wanted books out ("yes
        exclude").
      - A wanted book's page puts its buy links first ("yes").
      *Built so:*
      - "I want this book" is a second pill beside "I have this book" on a
        book's page, there while you don't have the book. A book is had or
        wanted, never both (migration 0078, `shelf_books.state`); a wanted
        one has no edition.
      - Search's "Only books on my shelf", and the count beside it, are of
        the books had: yours and those on shelves shared with you.
      - On a phone a wanted book's shops are above the page's buttons,
        across the page, moved in the document itself. On a wide screen
        they're beside the cover, where they were. They're placed as the
        page found the book: pressing the pill doesn't move them, since
        that would move the pill from under the finger.
      - The Shelf page has "Books you want" under your books, each with
        "I have it now" and "Take off"; the line at the top counts them
        apart ("2 books, and 1 wanted").
      - Merging two books keeps a book had over the same one wanted.
      - Claude's answers to the three things not asked, to overrule if
        wrong: wanted books are shared with the same groups as the rest
        of the shelf, since a shelf is shared whole, and the group's
        editors may take one off or say it's had; they show on the Shelf
        page under each shelf's books, yours and each shared with you;
        the count beside "Only books on my shelf" is of books had.
      - The first try put the shops beside the cover on a phone,
        under who wrote the book. The accessibility check failed it:
        "Bookshop.org" broke in two there. Above the buttons is the
        highest place with the page's width.
      - [ ] Not built: a list of wanted books to share outside a group
        (a gift list), and anything that says when a wanted book's price
        drops.
- [x] **Diets from Admin: adding, renaming and removing.** *Ray,
      2026-11-14: "ability for admin to create diets"; and, asked whether
      to rename and remove them too, and to set what a diet avoids only
      together: the first two, not the third ("B is fine").* (#186)
      - On Admin, under "Diets and what they avoid": "Add a diet" takes a
        name and what it avoids; "Change" on a diet now has its name as
        well, and "Remove…". Moderators, as for the rest of that panel.
      - A new diet's name that's taken is refused there (“Vegan” is a diet
        already), where a swap's form still gets the diet by that name.
      - Renaming keeps the tag, so recipes, sources and swaps have it
        under its new name.
      - Removing asks first, saying how many of the catalog's recipes and
        sources it comes off. It's one change in Recent changes, with what
        the diet avoided and where it was, and undoing that puts all of it
        back.
      - A diet with a swap recorded for it can't be removed: the form says
        how many, and links the ingredients whose pages they're on.
      - [ ] Undoing a removal is refused when a family's own recipe had the
        diet: a change that touched a family's collection isn't a
        moderator's to undo (routers/history.py). The question says so
        before removing, without saying whether one does; the count leaves
        families' recipes out for the same reason. Their recipes lose the
        tag like the catalog's. Splitting the removal in two, so the
        catalog's half could still be undone, would mend most of it.
      - [ ] What a diet avoids only together (Kosher: meat with milk) still
        has no form; Ray left it out of this.
      - A "Tag a recipe" suggestion for a diet since removed stays open,
        and accepting it is refused with "its recipe or its tag has gone.
        Dismiss it." (routers/suggestions.py, as it was).
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
      - [x] Using ratings (#166; *Ray, 2026-11-12*). A source's page and
        an author's show "Top rated": the recipes averaging four spoons or
        more, the best five, the higher average first and, level, the one
        more people rated; the section is left off when there are none.
        Search has a Sort: "Best match", as before, or "Highest rated",
        the rated recipes first that way and then the rest as they'd come.
        Sorted by rating, a rated recipe using one of your ingredients
        comes before an unrated one using them all.
      - [x] One person's five spoons tops a list (#181, in Top rated:
        see round 2's small fixes above). *Was: a least number of
        ratings would show nothing while the site is new; add one when
        there are enough to ask for. Ray's spec of 2026-11-13 asks for
        it now.*
      - [x] Ratings in the dumps (#168; *Ray, 2026-11-12*): each rated
        recipe's average and how many rated it, as its page shows them
        (recipe_ratings.csv; "spoons" and "ratings" on each recipe in the
        JSON). Never the ratings themselves, which say who gave what. The
        privacy page and the Open data page say so.
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

- [ ] **The notice beside allergen information isn't styled.** Found
      2026-11-15, reading App.vue for round 5. Its rule is written
      `.used-in /* … */ .allergen-notice`, a selector left half-finished
      when the grocery links went in (724f558), so it only matches a
      notice inside a "Used in" row, and there is none. The notice was
      meant to be small and muted (0.875rem, 48rem wide) and shows as an
      ordinary paragraph on a recipe's page, an ingredient's and the diet
      check. Not rendered and compared yet; for round 5's item 2, which
      is in the same stylesheet.

- [x] **Another way to say "Comes under" on an ingredient** (#196). *Ray,
      2026-11-14: "I don't like the verbiage 'comes under' for the
      ingredients"; 2026-11-15: "Counts as".* Done as round 5's first
      item, above.

- [x] **The accessibility check takes 40 seconds here, not thirteen minutes** (#187).
      *Ray, 2026-11-14, of a pull request's checks: "is there a way we can
      speed up tests?"* The check was the eleven minutes: one browser, and
      before every one of its 432 views a wait of at least 1.25s, which was
      nine of its ten minutes. Now four browsers look at once, and each
      looks when its page has stopped: loaded, every request it made
      answered, no "Loading…", fonts in, nothing still moving, three
      times running 50ms apart.
      - That it sees the same pages was measured, not supposed. Both
        checks were run on the same build with a count kept of each view's
        elements, words, height and width: 424 of 432 views the same.
        Both were run on a build with faults planted (faint words in the
        dark theme, and cells that don't wrap once their rows arrive): the
        old one failed 190 views, the new one those 190 with the same
        problems, and four more.
      - The eight views that differ are the notes on Saved, signed in.
        The old check had never seen them: going from /saved to
        /saved#notes is no load at all to Chrome, so the page stayed the
        signed-out one it already had, whoever the check then signed in
        as. They're loaded afresh now, and pass.
      - A page that hasn't stopped in ten seconds is looked at as it is,
        and named at the end with what it was waiting for. None does.
      - In CI, on this change's own run: the check 64 seconds where it
        was 611, and its job 1m58s where it was eleven minutes.
      - [ ] Now the longest of a pull request's checks is pytest: 2m16s
        in CI, of which the tests are 1m47s. Not looked at.

- [x] **Backspace and Delete in the search boxes** (#177). *Ray,
      2026-11-13: "we also need to be able to back space and delete in
      the search fields... it doesn't work today".* Tried with real key
      presses, both keys already edited what's typed in every search box.
      What they didn't do, and now do: in a box that holds its choices as
      chips (Search's "I have", "I don't have or don't want" and "In
      sources"; the larder picker's two), Backspace or Delete in the
      empty box takes the last chip away, where only its × did; and on
      the list of choices under a box, a letter, Backspace or Delete goes
      back to the box and acts there, where it did nothing. A held key
      doesn't go on from the text to the chips. That these are what Ray
      met is Claude's reading.
      - [ ] Not tried on a phone's own keyboard, only with a desktop's
        keys at a phone's width: some on-screen keyboards don't name the
        key they send.
      - [ ] The front page's "Cook with what you have" lists its choices
        under the box, not in it, so the keys don't take them there.
      - [ ] No test in CI presses keys: this was checked by a scratch
        browser run on the built image, which failed on the build before.

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
