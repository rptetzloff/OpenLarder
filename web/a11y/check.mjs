// Accessibility check: every kind of page, as the built app serves it, run
// through axe-core's WCAG 2.1 A and AA rules (contrast among them) in the
// light and dark themes, and checked for sideways scrolling on a phone: 360px
// wide, a touch screen, with a word of sixty letters in what people typed.
// Ray, 2026-11-08: "make sure we're passing accessibility checks, contrast,
// etc. along the way".
//
// It adds what it looks at through the API, as the people users.sql plants,
// so run it against a throwaway database only, with
// OPENLARDER_ARCHIVE_WEB_PAGES=false so web recipes ask the Internet Archive
// for nothing. It answers for cover pictures itself, so Open Library is asked
// for none either:
//
// A page also fails for breaking an ordinary word in two, which is what
// something squeezed does now that any word may break (BROKEN_WORDS).
//
//   psql "$DATABASE" -f a11y/users.sql
//   node a11y/check.mjs                 # A11Y_BASE, CHROME, A11Y_WORKERS to override
//
// Four browsers look at pages at once (fewer on a machine with fewer
// processors), each its own Chrome with its own cookies, and each looks at a
// page as soon as it has stopped (settle). Ray, 2026-11-14: "is there a way
// we can speed up tests?" It was one browser waiting at least 1.25s for
// every view: nine of the ten minutes it took.
//
// What axe can't judge (whether wording is clear, whether focus order makes
// sense, how a screen reader actually sounds) still needs a person.

import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { availableParallelism, tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.env.A11Y_BASE ?? "http://localhost:8000";
const CHROME =
  process.env.CHROME ??
  (process.platform === "win32"
    ? "C:/Program Files/Google/Chrome/Application/chrome.exe"
    : "/usr/bin/google-chrome");
const TOKENS = {
  admin: "a11y-check-token-admin-0123456789abcdef",
  cook: "a11y-check-token-cook-0123456789abcdef",
  // Signed in, with no name chosen yet: only the welcome page is theirs.
  new: "a11y-check-token-new-0123456789abcdef",
};
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const AXE = readFileSync(createRequire(import.meta.url).resolve("axe-core/axe.min.js"), "utf8");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const WORKERS = Math.max(1, Number(process.env.A11Y_WORKERS) || Math.min(4, availableParallelism()));
// The phone the layout is checked on (Ray's round 4 list, A4, 2026-11-14):
// 360px, the narrowest of the three widths the overflow was measured at, and
// a touch screen, because the rating's spoons are 44px wide only for a finger
// (pointer: coarse). At 390px with a mouse, as this was until then, a recipe's
// page passed while it was 24px too wide on a 384px phone.
const PHONE = 360;
// One word of sixty letters, which nothing but the page can break: what
// anyone may type as a title, a name or a note. (The dish in Aristophanes'
// Assemblywomen, cut short.) users.sql gives Cy a name of the same kind.
const LONG = "Lopadotemachoselachogaleokranioleipsanodrimhypotrimmatosilph";
// The words a page has broken in two. The long word breaks where it must
// because every word may (App.vue: overflow-wrap), and the cost of that is
// that something squeezed no longer runs over, where the layout check would
// see it; it breaks its words instead, "Inherited" into three lines of three
// letters. So an ordinary word, of up to twenty-five letters, in two pieces
// is a problem. Not on a drawn cover, whose title is fitted to it.
const BROKEN_WORDS = `(() => {
  const name = (e) => e.tagName.toLowerCase() + (typeof e.className === "string" && e.className ? "." + e.className.trim().split(/\\s+/).join(".") : "");
  const broken = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  for (let n; (n = walker.nextNode()); ) {
    const el = n.parentElement;
    if (!el || el.closest(".cover-blank, .visually-hidden, script, style")) continue;
    if (getComputedStyle(el).visibility === "hidden") continue;
    const runs = /\\S+/g;
    for (let run; (run = runs.exec(n.data)); ) {
      if (run[0].length > 25) continue;
      // A run may break at a hyphen or a slash; each word between them may not.
      const words = /[\\p{L}\\p{N}][\\p{L}\\p{N}'’.,:]*/gu;
      for (let word; (word = words.exec(run[0])); ) {
        if (word[0].length < 2) continue;
        range.setStart(n, run.index + word.index);
        range.setEnd(n, run.index + word.index + word[0].length);
        const lines = [...range.getClientRects()].filter((r) => r.width > 0);
        if (lines.length > 1 && Math.abs(lines[0].top - lines[lines.length - 1].top) > 2)
          broken.add('"' + word[0] + '" (' + name(el) + " in " + name(el.parentElement) + ")");
      }
    }
  }
  return [...broken].slice(0, 5);
})()`;
// A cover's picture, two pixels by three, for the one book users.sql gives a
// cover that arrives.
const COVER =
  "iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAIAAAA2iEnWAAAAEElEQVR42mPY6qUDRAwoFABM4AcD1RnCuAAAAABJRU5ErkJggg==";
// A source's page and an author's have their Top rated, which a change to
// what it waits for could quietly take out of the check.
const TOP_RATED_SHOWN = `document.querySelector("#top-rated-title + .top-rated li") ? "" : "Top rated isn't shown"`;
// The privacy page as it reads with ad clicks kept (adclicks.py), which is
// how the check's site runs: the longer page, with a section, a cookie and
// two sentences the other hasn't. Without this, a run with the setting
// left off would look at the shorter page and say nothing.
const AD_PRIVACY = `(() => {
  const section = document.querySelector("#from-an-ad");
  if (!section) return "The privacy page doesn't say what's kept from an ad click: is OPENLARDER_AD_CLICKS set?";
  const cookies = [...document.querySelectorAll("li code")].map((c) => c.textContent);
  return cookies.includes("ol_ad_click") ? "" : "The privacy page's cookies don't list ol_ad_click";
})()`;
// A book Cy wants (routers/shelf.py): "I want this book" is pressed on its
// page, and its shops are first on a phone, above the page's buttons, and
// beside the cover on a wide screen. And his shelf, and Ada's view of it, have
// what he wants under what he has.
const WANTED_BOOK = `(() => {
  const want = [...document.querySelectorAll(".shelf-pills button")].find((b) => b.textContent.trim() === "I want this book");
  if (!want) return "There's no “I want this book” on the book's page";
  if (want.getAttribute("aria-pressed") !== "true") return "“I want this book” isn't pressed for a book that's wanted";
  const buy = document.querySelector(".source-buy");
  if (!buy) return "The wanted book has no shops to buy it from";
  const narrow = matchMedia("(max-width: 40rem)").matches;
  const first = !!buy.closest("#source-buy-first");
  if (narrow && !first) return "On a phone the wanted book's shops aren't first";
  if (!narrow && first) return "On a wide screen the wanted book's shops have left the cover's side";
  if (narrow && !(buy.compareDocumentPosition(document.querySelector(".book-actions")) & Node.DOCUMENT_POSITION_FOLLOWING))
    return "The wanted book's shops aren't before its buttons in the document";
  return "";
})()`;
const WANTS_ON_SHELF = `(() => {
  const heads = [...document.querySelectorAll(".shelf-wants")];
  if (heads.length !== 1) return "The shelf page has " + heads.length + " lists of wanted books, not one";
  const cards = heads[0].nextElementSibling?.querySelectorAll(".cover-card").length ?? 0;
  return cards === 1 ? "" : "The wanted books' list has " + cards + " books, not the one planted";
})()`;
// Producers (producers.py): the check plants two, so their page has cards,
// the footer its link, an ingredient's page its card, and the privacy page
// and the terms their paragraphs. Without these a run that planted none
// would look at the emptier pages and say nothing.
const PRODUCERS_SHOWN = `(() => {
  const cards = document.querySelectorAll(".producer-list .producer-card").length;
  if (cards !== 2) return "The Producers page shows " + cards + " producers, not the two planted";
  if (!document.querySelector('.site-footer a[href="/producers"]')) return "The footer doesn't link the Producers page";
  for (const card of document.querySelectorAll(".producer-card")) {
    const link = card.querySelector('a[href^="/go/producer/"]');
    if (!link) return "A producer's card has no link";
    if (!link.nextElementSibling?.matches(".buy-note") || !link.nextElementSibling.textContent.trim())
      return "A producer's link doesn't say beside it what it earns";
  }
  return "";
})()`;
const PRODUCER_ON_INGREDIENT = `(() => {
  const cards = document.querySelectorAll(".from-producer .producer-card").length;
  return cards === 2 ? "" : "The ingredient's page shows " + cards + " producers, not the two that supply it";
})()`;
const PRODUCERS_SAID = `document.querySelector('main a[href="/producers"]') ? "" : "The page doesn't speak of producers"`;
// The admin bar: its links in the bar on a wide screen; on a phone one row,
// with the page's name on a button, and the links only once it's pressed.
const ADMIN_BAR = `(() => {
  const bar = document.querySelector("#admin-bar nav");
  const button = bar?.querySelector(".bar-toggle");
  if (!bar || !button) return "the admin bar isn't shown";
  const shown = [...bar.querySelectorAll("a")].filter((a) => a.getClientRects().length).length;
  if (innerWidth >= 640)
    return shown && !button.getClientRects().length ? "" : "the admin bar's links aren't in the bar on a wide screen";
  if (button.getAttribute("aria-expanded") === "true")
    return shown ? "" : "the admin bar's button didn't open its links";
  if (shown) return "the admin bar's links show on a phone before its button is pressed";
  const tall = Math.round(bar.getBoundingClientRect().height);
  if (tall > 56) return "the admin bar is " + tall + "px tall on a phone, more than one row";
  if (!button.textContent.includes("Flagged recipes")) return "the admin bar's button doesn't name the page";
  return "";
})()`;
// Search, kept to what can be made now: every recipe listed has everything,
// and with none to list, the next step is offered.
const MAKE_NOW = `(() => {
  if (document.querySelector("#search-show")?.value !== "0") return "a link's missing=0 isn't the choice shown";
  const hits = [...document.querySelectorAll(".hit")];
  if (hits.some((h) => !h.querySelector(".hit-have")?.textContent.includes("You have everything")))
    return "“Only what I can make now” lists a recipe that's missing something";
  if (!hits.length && !document.querySelector(".nothing button")?.textContent.includes("missing 2 or fewer"))
    return "an empty “Only what I can make now” doesn't offer two or fewer";
  return "";
})()`;
// A search link made before the form was rearranged opens the same search:
// its words in the bar, and what it leaves out shown where that now is.
const OLD_LINK = `(() => {
  if (document.querySelector("#search-title")?.value !== "biscuits") return "the link's title words aren't in the bar";
  if (document.querySelector(".more-toggle")?.getAttribute("aria-expanded") !== "true")
    return "More options isn't open for a link that uses one";
  if (![...document.querySelectorAll(".filter-chip")].some((c) => c.textContent.includes("Without Aged cheddar")))
    return "what the link leaves out isn't among the filters in use";
  return "";
})()`;
// On the sources page: the cover that arrived is shown, and the one that
// failed has left the printed face with its title, not a broken picture.
const COVERS_SHOWN = `(() => {
  const cover = (title) =>
    [...document.querySelectorAll(".cover-card")]
      .find((a) => a.querySelector("strong")?.textContent === title)
      ?.querySelector(".cover");
  const came = cover("Picture on the Cover");
  const lost = cover("Picture That Never Came");
  const picture = came?.querySelector("img.arrived");
  if (!picture || getComputedStyle(picture).opacity !== "1")
    return "the cover that arrived isn't shown";
  if (!lost || lost.querySelector("img")) return "the cover that failed left a picture behind";
  const face = lost.querySelector(".cover-title");
  if (face?.textContent !== "Picture That Never Came" || getComputedStyle(face).visibility !== "visible")
    return "the cover that failed didn't leave its title";
  return "";
})()`;

// The API, as one of the planted people.
async function api(path, who, body, method = body ? "POST" : "GET") {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      Cookie: `openlarder_session=${TOKENS[who]}`,
      // As the site's own pages: the API's rate limit leaves them alone.
      "Sec-Fetch-Site": "same-origin",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`${method} ${path}: ${res.status} ${JSON.stringify(data)}`);
  return data;
}

// One of each kind of source, with recipes, so every page has something on it.
async function seed() {
  const book = await api("/api/sources/manual", "admin", {
    title: "The A11y Kitchen",
    authors: ["Ann Author", "Pat Photographer"],
    year: 2020,
    // An ISBN, so its pages show buy links when an affiliate ID is set, as
    // CI's is (a made-up one; the check never follows a link).
    isbn: "9780393541113",
  });
  const edition = (await api(`/api/sources/${book.id}`, "admin")).editions[0].id;
  const recipe = (title, page, ingredients) =>
    api(`/api/sources/${book.id}/recipes`, "admin", {
      title,
      editions: [{ edition_id: edition, page }],
      ingredients,
    });
  const blend = await recipe("Biscuit Blend", "14", ["Glutinous rice flour", "Cornstarch"]);
  const biscuits = await recipe("Cheddar Biscuits", "22", [
    "Biscuit Blend (p. 14)",
    "Aged cheddar",
    "Butter or coconut oil",
    "Pie crust (p. 99)",
  ]);
  // Tags on the recipe and on its book, so both kinds of chip show.
  const allTags = await api("/api/tags", "admin");
  const tagged = (name) => allTags.find((t) => t.name === name).id;
  const vegetarian = tagged("Vegetarian");
  await api(`/api/recipes/${biscuits.id}/tags`, "admin", { tags: [vegetarian, tagged("Bread")] }, "PUT");
  await api(`/api/sources/${book.id}/tags`, "admin", { tags: [tagged("Gluten-Free")] }, "PUT");
  // A long title, so a table that can't wrap shows up at phone width (the
  // ingredient page's did, with real titles, before this was here).
  const slow = await recipe("Slow-Roasted Aged Cheddar and Caramelised Onion Biscuits with Brown Butter", "30", [
    "Aged cheddar",
    "Onion",
  ]);
  const ids = await api("/api/ingredients?q=cheddar", "admin");
  const cheddar = ids.ingredients.find((i) => i.name === "Aged cheddar").id;
  const cheese = (await api("/api/ingredients?q=butter", "admin")).ingredients[0].id;
  await api(`/api/ingredients/${cheddar}/parent`, "admin", { parent: cheese }, "PUT");

  // Two books whose titles the rules question as they arrive (title_rules.py),
  // for the Suggestions queue: one in sentence case, one missing an apostrophe.
  await api("/api/sources/manual", "admin", { title: "The grilling book", authors: ["Ann Author"] });
  await api("/api/sources/manual", "admin", {
    title: "Ann Authors Best Bakes",
    authors: ["Ann Author"],
  });
  const site = await api("/api/sources/websites", "admin", {
    address: "https://example.com/",
    name: "Example Kitchen",
  });
  const web = await api(`/api/sources/${site.id}/recipes`, "admin", {
    title: "Rhubarb Galette",
    web_address: "https://example.com/rhubarb-galette",
    ingredients: ["Rhubarb", "Butter"],
  });
  const magazine = await api("/api/sources/periodicals", "admin", { kind: "magazine", title: "Kitchen Monthly" });
  const issue = await api(`/api/sources/${magazine.id}/recipes`, "admin", {
    title: "Plum Torte",
    issue: "May 2024",
    issue_page: "42",
    ingredients: ["Plums", "Butter"],
  });
  const show = await api("/api/sources/shows", "admin", { kind: "tv_show", title: "Salt and Time" });
  const episode = await api(`/api/sources/${show.id}/recipes`, "admin", {
    title: "Buttermilk Chicken",
    episode: { season: 1, number: 2, title: "Salt", at: "12:34" },
    // Chicken, lemon and garlic: one of the front page's example searches,
    // so its chip is there to be checked.
    ingredients: ["Buttermilk", "Chicken", "Lemon", "Garlic"],
  });

  const box = await api("/api/sources/family", "cook", { title: "Gran's Box", acknowledged: true });
  const pie = await api(`/api/sources/${box.id}/recipes`, "cook", {
    title: "Sour Cream Raisin Pie",
    ingredients: ["Sour cream", "Raisins"],
  });
  const group = await api("/api/groups", "cook", { name: "The Cook family" });
  await api(`/api/groups/${group.id}/invites`, "cook", { role: "view" });
  await api(`/api/sources/${box.id}/groups`, "cook", { groups: [group.id] }, "PUT");
  const author = (await api(`/api/sources/${book.id}`, "admin")).credits[0].author_id;
  // A contributor's book and recipe, waiting for review.
  const waiting = await api("/api/sources/manual", "cook", { title: "Cy's Kitchen Notebook", authors: ["Cy Cook"] });
  const waitingBook = await api(`/api/sources/${waiting.id}`, "cook");
  await api(`/api/sources/${waiting.id}/recipes`, "cook", {
    title: "Waiting Pie",
    editions: [{ edition_id: waitingBook.editions[0].id, page: "3" }],
    ingredients: ["Apples", "Butter"],
  });
  // A change Cy suggests to a published recipe.
  const biscuitPage = await api(`/api/recipes/${biscuits.id}`, "admin");
  await api(`/api/recipes/${biscuits.id}/proposals`, "cook", {
    title: biscuitPage.title,
    editions: biscuitPage.pages.map((p) => ({ edition_id: p.edition_id, page: "31" })),
    ingredients: [...biscuitPage.ingredients, "Chives"],
    reason: "Page 31 in my printing.",
  });
  // And one to the book's details.
  const bookPage = await api(`/api/sources/${book.id}`, "admin");
  await api(`/api/sources/${book.id}/proposals`, "cook", {
    title: bookPage.title,
    subtitle: "Recipes for Every Reader",
    credits: bookPage.credits.map((c) => ({ author_id: c.author_id, name: c.credited_as, role: c.role })),
    editions: [],
    reason: "The cover has a subtitle.",
  });
  // Cy's larder: matched, unmatched, and out.
  const pantry = await api("/api/larder/lists", "cook", { name: "Pantry" });
  await api("/api/larder/lists", "cook", { name: "Spice drawer" });
  await api(`/api/larder/lists/${pantry.id}/items`, "cook", { name: "Aged cheddar" });
  await api(`/api/larder/lists/${pantry.id}/items`, "cook", { name: "Grandma's mystery jar" });
  const butter = await api(`/api/larder/lists/${pantry.id}/items`, "cook", { name: "Butter" });
  // Cy shares his pantry with his family group, which Ada joins to view.
  await api(`/api/larder/lists/${pantry.id}/groups`, "cook", { groups: [group.id] }, "PUT");
  const seat = await api(`/api/groups/${group.id}/invites`, "cook", { role: "view" });
  await api(`/api/invites/${seat.token}/accept`, "admin", {});
  await api(`/api/larder/items/${butter.id}`, "cook", { state: "out" }, "PATCH");
  // Cy owns the book, the edition with the recipe's page.
  await api(`/api/shelf/${book.id}`, "cook", { edition_id: biscuitPage.pages[0].edition_id }, "PUT");
  // And shares his shelf with the family group: Ada sees it.
  await api("/api/shelf/groups", "cook", { groups: [group.id] }, "PUT");
  // Cy wants to cook the biscuits, has cooked the blend, and shares the list.
  await api(`/api/saved/${biscuits.id}`, "cook", { state: "want" }, "PUT");
  await api(`/api/saved/${blend.id}`, "cook", { state: "cooked" }, "PUT");
  await api("/api/saved/groups", "cook", { groups: [group.id] }, "PUT");
  // Spoons from both, so a rating shows.
  await api(`/api/recipes/${biscuits.id}/rating`, "cook", { spoons: 5 }, "PUT");
  await api(`/api/recipes/${biscuits.id}/rating`, "admin", { spoons: 4 }, "PUT");
  // And on two more of the book's, one of them poor: Top rated is left off
  // until three of a source's recipes are rated (routers/ratings.py).
  await api(`/api/recipes/${blend.id}/rating`, "cook", { spoons: 4 }, "PUT");
  await api(`/api/recipes/${slow.id}/rating`, "admin", { spoons: 2 }, "PUT");
  // Cy's note on the biscuits, shared with the family; Ada's, her own.
  await api(`/api/recipes/${biscuits.id}/notes`, "cook", { body: "Double the cheddar.\nBake five minutes less.", groups: [group.id] }, "PUT");
  await api(`/api/recipes/${biscuits.id}/notes`, "admin", { body: "Good with soup.", groups: [] }, "PUT");
  // A problem reported with a recipe.
  await api("/api/reports", "cook", { kind: "recipe", id: biscuits.id, reason: "wrong", note: "Page 23 in mine." });
  // Requests: one asked for twice, one claimed, one declined.
  await api("/api/requests", "cook", { title: "Plenty", author: "Yotam Ottolenghi", note: "The vegetable one." });
  await api("/api/requests", "admin", { title: "plenty" });
  const claimed = await api("/api/requests", "cook", { title: "Salt, Fat, Acid, Heat", author: "Samin Nosrat" });
  await api(`/api/requests/${claimed.request.id}/claim`, "admin", {});
  const odd = await api("/api/requests", "cook", { title: "A Car Manual" });
  await api(`/api/requests/${odd.request.id}/decline`, "admin", { reason: "Not a cookbook." });

  // A book long enough that a phone lists only its first thirty recipes,
  // with shops, an edition and something rated, so every part that moves
  // on a phone is there to move.
  const long = await api("/api/sources/manual", "admin", {
    title: "Thirty-Two Bakes",
    authors: ["Ann Author"],
    year: 2021,
    isbn: "9780393541120",
  });
  const longEdition = (await api(`/api/sources/${long.id}`, "admin")).editions[0].id;
  for (let n = 1; n <= 32; n++) {
    const bake = await api(`/api/sources/${long.id}/recipes`, "admin", {
      title: `Bake Number ${n}`,
      editions: [{ edition_id: longEdition, page: String(n) }],
      ingredients: ["Flour", "Butter"],
    });
    // Three rated, as Top rated needs: five, four and three spoons.
    if (n <= 3) await api(`/api/recipes/${bake.id}/rating`, "cook", { spoons: 6 - n }, "PUT");
  }

  // The long word, wherever a person can type one: a book's title and its
  // author, a recipe's title (twice in the book, so both are flagged as
  // having the same title), an ingredient, and what's said about them.
  const wordy = await api("/api/sources/manual", "admin", {
    title: LONG,
    authors: [LONG],
    year: 2022,
    isbn: "9780393541137",
  });
  const wordyPage = await api(`/api/sources/${wordy.id}`, "admin");
  const wordyEdition = wordyPage.editions[0].id;
  const wordyRecipe = (page) =>
    api(`/api/sources/${wordy.id}/recipes`, "admin", {
      title: LONG,
      editions: [{ edition_id: wordyEdition, page }],
      ingredients: ["Aged cheddar", LONG],
    });
  const word = await wordyRecipe("1");
  await wordyRecipe("2");
  const address = `https://example.com/${LONG}/${LONG}?${LONG}=${LONG}`;
  await api("/api/reports", "cook", { kind: "recipe", id: word.id, reason: "wrong", note: `${LONG} ${address}` });
  await api(`/api/recipes/${word.id}/notes`, "cook", { body: `${LONG}\n${address}`, groups: [group.id] }, "PUT");
  await api(`/api/saved/${word.id}`, "cook", { state: "want" }, "PUT");
  await api(`/api/shelf/${wordy.id}`, "cook", { edition_id: wordyEdition }, "PUT");
  // And wants the long one, which has an ISBN and so shops to buy it from.
  await api(`/api/shelf/${long.id}`, "cook", { state: "want" }, "PUT");
  await api(`/api/recipes/${word.id}/rating`, "cook", { spoons: 5 }, "PUT");
  await api("/api/requests", "cook", { title: LONG, author: LONG, note: `${LONG} ${address}` });
  await api(`/api/larder/lists/${pantry.id}/items`, "cook", { name: LONG });
  // A click on its buy link, as a browser sends one (a click with no
  // browser's name is taken for a bot's and not counted), so Buy-link clicks
  // has the title to show. The shop it leads to is never asked for anything.
  const click = await fetch(`${BASE}/go/bookshop/${wordyEdition}?from=/sources/${wordy.id}`, {
    redirect: "manual",
    headers: { "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36" },
  });
  if (click.status < 300 || click.status >= 400) throw new Error(`The buy link answered ${click.status}`);
  // Two producers, switched on (producers.py): one as a farm would be set
  // up, one with the long word wherever an administrator types, earning
  // nothing and shipping everywhere. Both supply what aged cheddar is
  // under, so its page has both; and one has a click, for Buy-link clicks.
  for (const producer of [
    {
      key: "green-acre",
      label: "Green Acre Farm",
      description:
        "Grass-fed beef, pastured pork and farmstead butter from a family farm, sent frozen to your door.",
      offer: "New customers get $10 off their first order",
      ships_to: ["WI", "MN", "IL", "IA", "MI", "IN", "OH"],
      earns: "referral",
      note: "If you order through this link you get $10 off your first order, and the person who runs OpenLarder gets $20 in store credit at Green Acre Farm.",
    },
    { key: "long-mill", label: LONG, description: `${LONG} ${LONG}`, offer: LONG, ships_to: [], earns: "none", note: null },
  ]) {
    await api("/api/admin/shops", "admin", {
      ...producer,
      kind: "producer",
      builder: "direct",
      product_template: `https://producer.example/${producer.key}?ref=openlarder`,
      enabled: true,
      supplies: [cheese],
    });
  }
  const visit = await fetch(`${BASE}/go/producer/green-acre?from=/producers`, {
    redirect: "manual",
    headers: { "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36" },
  });
  if (visit.status < 300 || visit.status >= 400) throw new Error(`The producer's link answered ${visit.status}`);
  const wordyAuthor = wordyPage.credits[0].author_id;
  // The ingredient users.sql suggests links for, and has foods like.
  const oats = (await api("/api/ingredients?q=Quick-Cooking Oats", "admin")).ingredients.find(
    (i) => i.name === "Quick-Cooking Oats",
  ).id;
  const wordyIngredient = (await api(`/api/recipes/${word.id}`, "admin")).lines
    .flatMap((l) => l.options)
    .find((o) => o.ingredient?.name.toLowerCase() === LONG.toLowerCase()).ingredient.id;
  return { long, oats, wordy, word, wordyAuthor, wordyIngredient, waiting: waiting.id, vegetarian, book, blend, biscuits, site, web, magazine, issue, show, episode, box, pie, group, author, cheddar };
}

// Script that presses the button whose words begin so; with none, it throws,
// and the check stops, so a renamed button can't pass by showing nothing.
const press = (words) =>
  `[...document.querySelectorAll("main button")].find((b) => b.textContent.trim().startsWith(${JSON.stringify(words)})).click()`;

function pages(s) {
  // [path, who, how]: who is signed in, or nobody. how.phone: axe at the
  // phone's width too, for a page that shows a phone something of its
  // own; how.then: script to run there first, for a state a click makes;
  // how.expect: script that answers what the page shows wrongly, or nothing.
  return [
    ["/", null],
    ["/", "admin"],
    ["/search", null],
    [`/search?i=${s.cheddar}`, null],
    ["/search?q=biscuits", null],
    ["/search?q=biscuits&kind=book&kind=website", null],
    [`/search?tag=${s.vegetarian}`, null],
    [`/search?q=biscuits&x=${s.cheddar}`, null, { expect: OLD_LINK }],
    ["/sources", null, { expect: COVERS_SHOWN }],
    ["/sources", "cook"],
    ["/sources", "admin"],
    ["/sources?kind=book&kind=website&sort=recipes", null],
    [`/sources/${s.book.id}`, null, { expect: TOP_RATED_SHOWN }],
    [`/sources/${s.book.id}`, "admin"],
    [`/sources/${s.site.id}`, null],
    [`/sources/${s.magazine.id}`, null],
    [`/sources/${s.show.id}`, null],
    [`/sources/${s.box.id}`, "cook"],
    [`/sources/${s.book.id}/edit`, "admin"],
    [`/sources/${s.book.id}/recipes/new`, "admin"],
    [`/sources/${s.show.id}/recipes/new`, "admin"],
    [`/sources/${s.box.id}/recipes/new`, "cook"],
    [`/sources/${s.book.id}/bulk`, "admin"],
    [`/recipes/${s.biscuits.id}`, null],
    [`/recipes/${s.biscuits.id}`, "admin"],
    [`/recipes/${s.web.id}`, null],
    [`/recipes/${s.issue.id}`, null],
    [`/recipes/${s.episode.id}`, null],
    [`/recipes/${s.pie.id}`, "cook"],
    [`/recipes/${s.biscuits.id}/edit`, "admin"],
    ["/ingredients", null],
    ["/ingredients?top=true&sort=name", null],
    [`/ingredients/${s.cheddar}`, null],
    [`/ingredients/${s.cheddar}`, "admin"],
    ["/authors", null],
    ["/authors?sort=recipes&kind=person", null],
    [`/authors/${s.author}`, null, { expect: TOP_RATED_SHOWN }],
    [`/authors/${s.author}`, "admin"],
    ["/groups", "cook"],
    [`/groups/${s.group.id}`, "cook"],
    ["/invite/not-a-real-invite", null],
    ["/account", "cook"],
    ["/account/flags", "admin"],
    ["/admin", "admin"],
    ["/admin/flags", "admin", { expect: ADMIN_BAR }],
    ["/admin/imports", "admin"],
    ["/admin/suggestions", "admin"],
    ["/admin/api", "admin"],
    ["/admin/clicks", "admin"],
    ["/admin/merges", "admin"],
    ["/admin/shops", "admin"],
    ["/admin/shops", "cook"],
    ["/admin/links", "admin"],
    ["/admin/people", "admin"],
    ["/admin/changes", "admin"],
    ["/admin/review", "admin"],
    ["/admin/reports", "admin"],
    [`/sources/${s.waiting}`, "cook"],
    [`/recipes/${s.biscuits.id}/propose`, "cook"],
    [`/sources/${s.book.id}/propose`, "cook"],
    [`/recipes/${s.biscuits.id}`, "cook"],
    ["/account", "admin"],
    ["/requests", null],
    ["/requests", "cook"],
    ["/admin/suggestions", "cook"],
    ["/data", null],
    ["/larder", "cook"],
    ["/larder", "admin"],
    ["/search?larder=1", "cook"],
    ["/larder", null],
    ["/shelf", "cook", { phone: true, expect: WANTS_ON_SHELF }],
    ["/shelf", "admin", { phone: true, expect: WANTS_ON_SHELF }],
    ["/shelf", null],
    // The book Cy wants: its shops first, on a phone.
    [`/sources/${s.long.id}`, "cook", { phone: true, expect: WANTED_BOOK }],
    ["/saved", "cook"],
    ["/saved", "admin"],
    ["/saved", null],
    ["/saved#notes", "cook"],
    ["/saved#notes", "admin"],
    ["/search?sv=1", "cook"],
    [`/sources/${s.book.id}`, "cook"],
    ["/search?own=1&q=biscuit", "cook"],
    ["/privacy", null, { expect: `(${AD_PRIVACY}) || (${PRODUCERS_SAID})` }],
    ["/privacy", null, { phone: true, expect: `(${AD_PRIVACY}) || (${PRODUCERS_SAID})` }],
    ["/terms", null, { expect: PRODUCERS_SAID }],
    // Producers: their page, with a card's list of states opened on a phone;
    // and on the page of an ingredient under what they supply.
    ["/producers", null, { expect: PRODUCERS_SHOWN }],
    ["/producers", "cook", { expect: PRODUCERS_SHOWN }],
    [
      "/producers",
      null,
      { phone: true, then: `document.querySelector(".producer-card details summary").click()`, expect: PRODUCERS_SHOWN },
    ],
    [`/ingredients/${s.cheddar}`, null, { phone: true, expect: PRODUCER_ON_INGREDIENT }],
    ["/welcome", "new"],
    ["/sign-in-failed", null],
    // A long book: on a phone its parts are in another order, with the
    // first thirty recipes; then with all of them shown.
    [`/sources/${s.long.id}`, null, { phone: true, expect: TOP_RATED_SHOWN }],
    [
      `/sources/${s.long.id}`,
      "cook",
      { phone: true, then: `document.querySelector(".show-all button").click()` },
    ],
    // Ingredient links' other tables, and the two forms a moderator opens on
    // an ingredient's page: on a phone each is laid out for one.
    ["/admin/links", "admin", { phone: true, then: press("Unsure foods") }],
    ["/admin/links", "admin", { phone: true, then: press("Other names") }],
    [`/ingredients/${s.oats}`, "admin", { phone: true, then: press("+ Record") }],
    [`/ingredients/${s.oats}`, "admin", { phone: true, then: press("+ Link") }],
    // The admin bar on a phone, opened; and an admin page's "How this
    // works", which is closed until asked for.
    [
      "/admin/flags",
      "admin",
      { phone: true, then: `document.querySelector(".bar-toggle").click()`, expect: ADMIN_BAR },
    ],
    [
      "/admin/suggestions",
      "admin",
      { phone: true, then: `document.querySelector("main details.how").open = true` },
    ],
    // Search: "More options" opened, signed out and with a larder; the
    // filters opened on a phone; and kept to what can be made now, with
    // recipes to list and with none.
    ["/search", null, { phone: true, then: `document.querySelector(".more-toggle").click()` }],
    ["/search?larder=1", "cook", { phone: true, then: `document.querySelector(".more-toggle").click()` }],
    [
      `/search?tag=${s.vegetarian}`,
      null,
      { phone: true, then: `document.querySelector(".filters-toggle").click()` },
    ],
    [`/search?i=${s.cheddar}&missing=0`, null, { phone: true, expect: MAKE_NOW }],
    [`/search?i=${s.cheddar}&missing=0&tag=${s.vegetarian}`, null, { phone: true, expect: MAKE_NOW }],
    // What a phone folds away, opened: a flag being dismissed, a change's
    // rows, the ways to add a source, and what changes a book.
    [
      "/admin/flags",
      "admin",
      {
        phone: true,
        then: `[...document.querySelectorAll(".flag-actions button")].find((b) => b.textContent.includes("Dismiss")).click()`,
      },
    ],
    ["/admin/changes", "admin", { phone: true, then: `document.querySelector(".change-more").click()` }],
    ["/sources", "admin", { phone: true, then: `document.querySelector(".add-toggle").click()` }],
    [`/sources/${s.book.id}`, "admin", { phone: true, then: `document.querySelector(".fold-toggle").click()` }],
    // Shops: one being changed, with a link tried; and one being added.
    [
      "/admin/shops",
      "admin",
      {
        phone: true,
        then: `(async () => {
          document.querySelector(".shop-controls [data-edit]").click();
          await new Promise((r) => setTimeout(r, 100));
          [...document.querySelectorAll(".shop-form button")].find((b) => b.textContent.trim() === "Test link").click();
        })()`,
      },
    ],
    ["/admin/shops", "admin", { phone: true, then: `document.querySelector("[data-add]").click()` }],
    // A producer being changed, with what it supplies; and one being added.
    [
      "/admin/shops",
      "admin",
      { phone: true, then: `document.querySelector('section[aria-labelledby="shops-producer"] [data-edit]').click()` },
    ],
    ["/admin/shops", "admin", { phone: true, then: `document.querySelector('[data-add="producer"]').click()` }],
    // Admin's diets: one being changed, and one being added.
    ["/admin", "admin", { phone: true, then: `document.querySelector(".diet-avoids .change").click()` }],
    ["/admin", "admin", { phone: true, then: `document.querySelector(".diet-avoids .add-diet").click()` }],
    // The long word's own pages. Its other places are on pages above: both
    // lists of flags, the reports, the clicks, the requests, Cy's larder,
    // shelf and saved recipes, the lists of sources, ingredients and authors.
    [`/sources/${s.wordy.id}`, null],
    [`/sources/${s.wordy.id}`, "admin"],
    [`/sources/${s.wordy.id}`, "cook"],
    [`/sources/${s.wordy.id}/edit`, "admin"],
    [`/sources/${s.wordy.id}/bulk`, "admin"],
    [`/recipes/${s.word.id}`, null],
    [`/recipes/${s.word.id}`, "admin"],
    [`/recipes/${s.word.id}`, "cook"],
    [`/recipes/${s.word.id}/edit`, "admin"],
    [`/authors/${s.wordyAuthor}`, null],
    [`/authors/${s.wordyAuthor}`, "admin"],
    [`/ingredients/${s.wordyIngredient}`, null],
    [`/ingredients/${s.wordyIngredient}`, "admin"],
    [`/search?q=${LONG}`, null],
    [`/search?i=${s.wordyIngredient}`, "cook"],
  ];
}

// Chrome over the DevTools protocol, as the render checks drive it.
const PORT = 9400 + Math.floor(Math.random() * 400);
async function browser(n) {
  const port = PORT + n;
  const proc = spawn(CHROME, [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${join(tmpdir(), `openlarder-a11y-${port}`)}`,
    "about:blank",
  ]);
  let ws;
  for (let i = 0; i < 100 && !ws; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) ws = new WebSocket(page.webSocketDebuggerUrl);
    } catch {}
    if (!ws) await sleep(200);
  }
  if (!ws) throw new Error(`Chrome didn't start (${CHROME})`);
  await new Promise((r) => ws.addEventListener("open", r));
  let id = 0;
  const pending = new Map();
  const failures = [];
  // What the page is still waiting for (settle): its requests not yet
  // answered, and whether the document asked for has loaded. Both are kept
  // by the document they belong to (Chrome's loader id), since the page
  // before can still be asking, or only now saying it has loaded, as it's
  // left: a recipe form's check of its lines was waited ten seconds for by
  // the page after it.
  const inflight = new Map();
  const state = { loader: "", loaded: new Set() };
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) {
      pending.get(m.id)(m);
      pending.delete(m.id);
    }
    // Not the tab's icon: Chrome asks for that itself, and was seen never
    // to say it had come.
    if (m.method === "Network.requestWillBeSent" && !m.params.request.url.includes("/favicon."))
      inflight.set(m.params.requestId, { url: m.params.request.url, loader: m.params.loaderId });
    if (m.method === "Network.loadingFinished" || m.method === "Network.loadingFailed")
      inflight.delete(m.params.requestId);
    if (m.method === "Page.lifecycleEvent" && m.params.name === "load")
      state.loaded.add(m.params.loaderId);
    if (m.method === "Runtime.exceptionThrown")
      failures.push(m.params.exceptionDetails?.exception?.description?.split("\n")[0]);
    // The check answers for covers itself, so the app asks Open Library for
    // none: cover 1 is a picture, and any other fails (users.sql has one of each).
    if (m.method === "Fetch.requestPaused") {
      const { requestId, request } = m.params;
      if (request.url.includes("/covers/1-"))
        send("Fetch.fulfillRequest", {
          requestId,
          responseCode: 200,
          responseHeaders: [{ name: "Content-Type", value: "image/png" }],
          body: COVER,
        });
      else send("Fetch.failRequest", { requestId, errorReason: "Failed" });
    }
  });
  const send = (method, params = {}) =>
    new Promise((r) => {
      const n = ++id;
      pending.set(n, r);
      ws.send(JSON.stringify({ id: n, method, params }));
    });
  const evaluate = async (expression) => {
    const m = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (m.result?.exceptionDetails) throw new Error(m.result.exceptionDetails.exception?.description);
    return m.result?.result?.value;
  };
  await send("Page.enable");
  await send("Page.setLifecycleEventsEnabled", { enabled: true });
  await send("Runtime.enable");
  await send("Network.enable");
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/covers/*" }] });
  return { send, evaluate, failures, inflight, state, close: () => (ws.close(), proc.kill()) };
}

// Pages load their data after they're drawn: "Loading…" is still up, or a
// recipe's ingredient lines aren't checked yet. And a font not yet in, or
// something still moving (a cover fading in), would be measured as it won't
// stay.
const BUSY = `[
  document.readyState !== "complete" && "the document",
  /Loading…/.test(document.querySelector("main")?.innerText ?? "") && "“Loading…”",
  !!document.querySelector(".line-row input:not(:placeholder-shown)") && !document.querySelector(".line-tag") && "the ingredient lines' check",
  document.fonts.status !== "loaded" && "a font",
  document.getAnimations().some((a) => a.playState === "running" && Number.isFinite(a.effect?.getComputedTiming().endTime)) && "something moving",
].filter(Boolean).join(", ")`;
const QUIET = 3;

// Waits for the page to stop: loaded, nothing asked for and not yet answered,
// and nothing BUSY, three times running, 50ms apart. What an answer sets off
// (another request, a redraw) starts at once, so a page quiet that long has
// finished. Answers nothing, or what it was still waiting for after ten
// seconds: that one is looked at as it is, and named at the end.
async function settle(b) {
  const until = Date.now() + 10_000;
  let quiet = 0;
  let busy = "";
  while (quiet < QUIET && Date.now() < until) {
    await sleep(50);
    if (!b.state.loaded.has(b.state.loader)) busy = "the page to load";
    else
      busy = [...b.inflight.values()]
        .filter((r) => r.loader === b.state.loader)
        .map((r) => r.url)
        .join(", ");
    // Mid-load there's no page to answer, and that isn't quiet.
    busy ||= (await b.evaluate(BUSY)) ?? "the page to answer";
    quiet = busy ? 0 : quiet + 1;
  }
  return busy;
}

// Loads a page afresh, and waits for it. From /saved to /saved#notes is no
// load at all to Chrome, and the page stays as whoever was signed in before
// saw it: every view of the notes had been the signed-out page. That one
// goes by way of an empty page, so it's loaded like any other.
async function go(b, url) {
  let went = await b.send("Page.navigate", { url });
  if (!went.result?.loaderId) {
    await b.send("Page.navigate", { url: "about:blank" });
    went = await b.send("Page.navigate", { url });
    if (!went.result?.loaderId) throw new Error(`${url} wasn't loaded afresh`);
  }
  // This document's from here on; what the ones before left is dropped.
  b.state.loader = went.result.loaderId;
  b.state.loaded = new Set([...b.state.loaded].filter((id) => id === b.state.loader));
  for (const [id, r] of b.inflight) if (r.loader !== b.state.loader) b.inflight.delete(id);
  return settle(b);
}

// axe's WCAG A and AA rules on the page as it is: what fails, and what it
// couldn't decide (contrast over an image, say), which is reported, not failed.
async function runAxe(b) {
  if (!(await b.evaluate("typeof axe !== 'undefined'"))) await b.evaluate(AXE);
  return b.evaluate(
    `axe.run(document, { runOnly: { type: "tag", values: ${JSON.stringify(TAGS)} } }).then(r => ({ incomplete: r.incomplete.map(v => ({ id: v.id, nodes: v.nodes.slice(0, 2).map(n => n.target.join(" ")) })), violations: r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 3).map(n => n.target.join(" ") + (n.any[0]?.message ? " — " + n.any[0].message : "")) })) }))`,
  );
}

// Against the width asked for, not innerWidth: with a phone's emulation the
// browser widens its layout viewport to fit what's too wide, so innerWidth
// grows with the overflow and hides anything short of extreme.
const overflowOf = (b, width) => b.evaluate(`document.documentElement.scrollWidth - ${width}`);

// The control: a page with problems planted in it must fail, or a clean run
// means nothing (the checker isn't running, or isn't looking).
async function control(b) {
  await phone(b, PHONE);
  await go(b, `${BASE}/privacy`);
  // Too wide by 20px, which is less than a recipe's page was over by. (As
  // wide as the screen exactly isn't too wide at all: main has no padding
  // of its own, and the control said so.)
  await b.evaluate(
    `document.querySelector("main").insertAdjacentHTML("beforeend", '<p style="color:#ccc;background:#fff">faint</p><img src="/x.png"><div style="width:${PHONE + 20}px">wide</div><p style="width:2rem">Breakfast</p>')`,
  );
  const found = (await runAxe(b)).violations.map((v) => v.id);
  const wide = await overflowOf(b, PHONE);
  const missed = ["color-contrast", "image-alt"].filter((id) => !found.includes(id));
  if (wide <= 0) missed.push("overflow");
  if (!(await b.evaluate(BROKEN_WORDS)).some((w) => w.startsWith('"Breakfast"'))) missed.push("a broken word");
  if (missed.length)
    throw new Error(`The control wasn't caught (missed ${missed.join(", ")}); the check proves nothing.`);
  // What's only too wide under a finger is missed if the phone has a mouse.
  if (!(await b.evaluate(`matchMedia("(pointer: coarse)").matches`)))
    throw new Error("The phone isn't a touch screen; what's sized for a finger isn't being checked.");
}

// The screen a page is looked at on: under 600px it's a phone, with a finger.
async function phone(b, width) {
  await b.send("Emulation.setDeviceMetricsOverride", {
    width,
    height: 900,
    deviceScaleFactor: 1,
    mobile: width < 600,
  });
  await b.send("Emulation.setTouchEmulationEnabled", { enabled: width < 600, maxTouchPoints: 5 });
}

// One view: what's wrong with it, what axe couldn't decide, and what it was
// still waiting for if it never stopped.
async function check(b, path, who, theme, width, how = {}) {
  await b.send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-color-scheme", value: theme }],
  });
  await phone(b, width);
  await b.send("Network.clearBrowserCookies");
  if (who)
    await b.send("Network.setCookie", {
      name: "openlarder_session",
      value: TOKENS[who],
      url: `${BASE}/`,
      httpOnly: true,
    });
  let busy = await go(b, `${BASE}${path}`);
  if (how.then && width < 600) {
    await b.evaluate(how.then);
    busy = (await settle(b)) || busy;
  }
  const problems = [];
  const undecided = [];
  // What the page should be showing, where an entry says: its answer is
  // what's wrong, or nothing.
  if (how.expect) {
    const wrong = await b.evaluate(how.expect);
    if (wrong) problems.push(wrong);
  }
  const overflow = await overflowOf(b, width);
  if (overflow > 0) problems.push(`scrolls sideways by ${overflow}px at ${width}px wide`);
  for (const word of await b.evaluate(BROKEN_WORDS)) problems.push(`breaks ${word} in two`);
  // axe once per theme and page, at desktop width; the phone pass is for
  // layout, unless the page shows a phone something of its own.
  if (width >= 600 || how.phone) {
    const { violations, incomplete } = await runAxe(b);
    for (const v of violations)
      problems.push(`${v.id} (${v.impact}): ${v.help}\n      ${v.nodes.join("\n      ")}`);
    for (const v of incomplete)
      for (const node of v.nodes) undecided.push(`${v.id}: ${path} (${theme}) ${node}`);
  }
  return { problems, undecided, busy };
}

const s = await seed();
const views = [];
for (const theme of ["light", "dark"])
  for (const [path, who, how] of pages(s))
    for (const width of [1280, PHONE]) views.push({ path, who, theme, width, how });
const browsers = await Promise.all(
  Array.from({ length: Math.min(WORKERS, views.length) }, (_, n) => browser(n)),
);
// Each browser takes the next view not yet taken; what they find is kept by
// the view's place, so it's printed in the order it always was.
const found = new Array(views.length);
let next = 0;
let failed = 0;
try {
  await control(browsers[0]);
  await Promise.all(
    browsers.map(async (b) => {
      for (let n = next++; n < views.length; n = next++) {
        const v = views[n];
        found[n] = await check(b, v.path, v.who, v.theme, v.width, v.how);
      }
    }),
  );
  for (const b of browsers)
    for (const f of b.failures) {
      failed++;
      console.log(`✗ script error: ${f}`);
    }
} finally {
  for (const b of browsers) b.close();
}
const checked = views.length;
const named = (v) => `${v.path} (${v.who ?? "signed out"}, ${v.theme}, ${v.width}px)`;
views.forEach((v, n) => {
  if (!found[n].problems.length) return;
  failed++;
  console.log(`✗ ${named(v)}`);
  for (const p of found[n].problems) console.log(`    ${p}`);
});
const undecided = new Set(found.flatMap((f) => f.undecided));
if (undecided.size) {
  console.log("For a person to look at, where axe couldn't decide:");
  for (const where of undecided) console.log(`    ${where}`);
}
if (found.some((f) => f.busy)) {
  console.log("Still busy after ten seconds, and looked at as they were:");
  views.forEach((v, n) => found[n].busy && console.log(`    ${named(v)}: waiting for ${found[n].busy}`));
}
console.log(
  `${checked} page views checked (axe at 1280px, and at ${PHONE}px where a phone has its own; layout at ${PHONE}px, as a touch screen), ${failed} with problems.`,
);
process.exit(failed ? 1 : 0);
