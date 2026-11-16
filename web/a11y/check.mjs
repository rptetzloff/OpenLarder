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
// Between a phone and a desktop (Ray's round 5 list, item 2, 2026-11-15): a
// tablet, a small laptop window, a phone held sideways. Nothing looked
// there, and an ingredient's table, the flags, Buy-link clicks and the
// signed-in header were all too wide or squeezed somewhere from 640px to
// 1100px. Layout only, in one theme (a page is as wide in the dark), and
// signed in, since the header with a name in it is the widest: Cy's name
// is thirty-two letters. A small tablet, a large one and a small laptop,
// which are the list's three; and 900px, the first step past 56rem, where
// the header's full row and the tables come back with the least room they
// will ever have (a sweep of every 20px found three pages the other three
// widths passed, nearly all of it from 900px to 960px).
// A11Y_BETWEEN=640,660,… looks at others, for a sweep.
const BETWEEN = process.env.A11Y_BETWEEN?.split(",").map(Number) ?? [700, 820, 900, 1024];
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
// A table's cells that are squeezed: narrower than 6rem and holding more
// than three lines (Ray's round 5 list, 2e). A column can be left almost no
// room and still not run over, now that any word may break: an ingredient's
// Source column was 71px at 820px, with a book's title down six lines of it.
// Lines are counted by where the text's boxes sit, so two sizes of text on
// one line are one line.
const SQUEEZED_CELLS = `(() => {
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
  const squeezed = [];
  const range = document.createRange();
  for (const cell of document.querySelectorAll("td, th")) {
    const box = cell.getBoundingClientRect();
    if (box.width === 0 || box.width >= 6 * rem) continue;
    range.selectNodeContents(cell);
    const boxes = [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0).sort((a, b) => a.top - b.top);
    let lines = 0;
    let bottom = -Infinity;
    for (const r of boxes) {
      if (r.top >= bottom - 1) lines++;
      bottom = Math.max(bottom, r.bottom);
    }
    if (lines > 3)
      squeezed.push(JSON.stringify(cell.textContent.trim().replace(/\\s+/g, " ").slice(0, 40)) + " is " + lines + " lines in a cell " + Math.round(box.width) + "px wide");
  }
  return squeezed.slice(0, 5);
})()`;
// A cover's picture, two pixels by three, for the one book users.sql gives a
// cover that arrives.
const COVER =
  "iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAIAAAA2iEnWAAAAEElEQVR42mPY6qUDRAwoFABM4AcD1RnCuAAAAABJRU5ErkJggg==";
// A source's page and an author's have their Top rated, which a change to
// what it waits for could quietly take out of the check.
// A recipe in a list has its source's cover beside it: the picture, or a
// block of the colour its drawn cover has (Ray's round 5 list, item 3,
// 2026-11-15). Where there was no picture it was an empty box, white on
// the page, and nearly every source here has no picture.
const THUMBS_DRAWN = `(() => {
  const thumbs = [...document.querySelectorAll(".hit .hit-cover")];
  if (!thumbs.length) return "No recipe in the list has a cover beside it";
  const page = getComputedStyle(document.body).backgroundColor;
  for (const thumb of thumbs) {
    if (thumb.querySelector("img.arrived")) continue;
    const colour = getComputedStyle(thumb).backgroundColor;
    if (!thumb.style.getPropertyValue("--cover") || colour === page || colour === "rgba(0, 0, 0, 0)")
      return "A recipe's cover is an empty box (" + colour + "), not its source's colour";
  }
  return "";
})()`;
// And the two books users.sql gives pictures (one that arrives, one that
// fails) each have a recipe, so a search for both shows a thumbnail with
// its picture and one left as its block.
const THUMB_PICTURES = `(() => {
  const thumb = (source) =>
    [...document.querySelectorAll(".hit")]
      .find((h) => [...h.querySelectorAll("a")].some((a) => a.textContent.trim() === source))
      ?.querySelector(".hit-cover");
  const came = thumb("Picture on the Cover");
  const lost = thumb("Picture That Never Came");
  if (!came || !lost) return "The recipes of the two books with pictures aren't in the results";
  const picture = came.querySelector("img.arrived");
  if (!picture || getComputedStyle(picture).opacity !== "1")
    return "the cover that arrived isn't shown beside its recipe";
  if (lost.querySelector("img")) return "the cover that failed left a picture behind beside its recipe";
  return "";
})()`;
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
// A link to a shop is an outline button, on a recipe's page and a book's
// alike (Ray's round 5 list, item 7, 2026-11-15: a book's were dark bars,
// and the two pages disagreed).
const BUY_OUTLINED = `(() => {
  const links = [...document.querySelectorAll("main a.buy-button")].filter((a) => a.getClientRects().length);
  if (!links.length) return "The page has no links to shops";
  const token = (name) => {
    const probe = document.createElement("span");
    probe.style.color = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    document.body.append(probe);
    const colour = getComputedStyle(probe).color;
    probe.remove();
    return colour;
  };
  for (const link of links) {
    const style = getComputedStyle(link);
    if (style.backgroundColor !== token("--surface") || style.color !== token("--fg") || style.borderTopWidth !== "1px" || style.borderTopColor !== token("--border"))
      return "The link to " + link.textContent.trim() + " isn't an outline button: " + style.backgroundColor + " with a " + style.borderTopWidth + " border";
    if (link.getBoundingClientRect().height < 44) return "The link to " + link.textContent.trim() + " is under 44px tall";
  }
  return "";
})()`;
// And on a book's page they are under a heading for each format, each only
// its shop's name, and named in full for a screen reader: "Print" on a
// button read as printing the page. Two to a row on a phone, where the box
// is the screen's width, and one to a row beside the cover.
const BUY_BY_FORMAT = `(() => {
  const box = document.querySelector(".source-buy");
  if (!box) return "The book has no shops to buy it from";
  const said = { "Print book": "print book", "Ebook": "ebook" };
  const heads = [...box.querySelectorAll("h3")];
  if (!heads.length) return "The book's shops aren't under a heading for their format";
  let links = 0;
  for (const head of heads) {
    const format = said[head.textContent.trim()];
    if (!format) return "The book's shops are under a heading that says " + JSON.stringify(head.textContent.trim());
    const shops = [...(head.nextElementSibling?.querySelectorAll("a.buy-button") ?? [])];
    if (!shops.length) return "The heading " + JSON.stringify(head.textContent.trim()) + " has no shop under it";
    links += shops.length;
    const wrong = shops.find((a) => a.getAttribute("aria-label") !== "Buy the " + format + " at " + a.textContent.trim());
    if (wrong) return "The link to " + wrong.textContent.trim() + " is named " + JSON.stringify(wrong.getAttribute("aria-label"));
    if (shops.length > 1) {
      const beside = Math.abs(shops[0].getBoundingClientRect().top - shops[1].getBoundingClientRect().top) < 2;
      const narrow = matchMedia("(max-width: 40rem)").matches;
      if (narrow && !beside) return "On a phone the book's shops aren't two to a row";
      if (!narrow && beside) return "Beside the cover the book's shops aren't one to a row";
    }
  }
  if (links !== box.querySelectorAll("a.buy-button").length) return "A link to a shop isn't under a format's heading";
  if (![...box.querySelectorAll(".buy-note a")].some((a) => a.textContent.trim() === "How this works")) return "The book's shops don't say how the links work";
  return "";
})()`;
// Your shelf, Your larder and Saved recipes (Ray's round 5 list, item 8,
// 2026-11-15): one sentence under the heading, who can see it, and how the
// page works folded under it. Closed where there's something on the page;
// open where there's nothing, which is when it's wanted.
const HOW_FOLDED = (open) => `(() => {
  const intro = document.querySelector("main .list-head p");
  const how = document.querySelector("main .list-head + details.how");
  if (!intro) return "The page has no sentence under its heading";
  if (!how) return "The page has no “How this works” under its heading";
  const words = intro.textContent.trim();
  if (!words.startsWith("Only you see") || words.split(". ").length > 1)
    return "Under the heading isn't the one sentence, who can see it: " + JSON.stringify(words.slice(0, 60));
  if (how.querySelector("summary").textContent.trim() !== "How this works") return "The folded part isn't called “How this works”";
  if (!how.querySelector("p")?.textContent.trim()) return "“How this works” has nothing in it";
  if (how.open !== ${open}) return "“How this works” is " + (how.open ? "open" : "closed") + ${JSON.stringify(open ? " on a page with nothing on it" : " on a page with something on it")};
  // On a phone its row is 44px to tap, in space it takes back from the
  // sentence above and the row below (Ray, 2026-11-15: "a little less
  // padding"): neither may be inside it.
  if (innerWidth < 640) {
    const row = how.querySelector("summary").getBoundingClientRect();
    if (row.height < 44) return "“How this works” is " + Math.round(row.height) + "px to tap on a phone, under 44px";
    if (intro.getBoundingClientRect().bottom > row.top) return "“How this works” is over the sentence above it";
    const after = (how.open ? how.querySelector("p") : how.nextElementSibling)?.getBoundingClientRect();
    if (after && after.top < row.bottom) return "“How this works” is over what comes after it";
  }
  return "";
})()`;
// Your account: the agreement, once accepted, is the day it was and its
// words folded under "Read the agreement" (the same item: in full it made
// the page 2,734px on a phone).
const AGREEMENT_FOLDED = `(() => {
  const panel = document.querySelector(".agreement-panel");
  if (!panel) return "Your account has no contributor agreement";
  const said = panel.querySelector(".status")?.textContent.trim() ?? "";
  if (!said.startsWith("Accepted on ") || !said.includes(String(new Date().getFullYear()))) return "The agreement doesn't say when it was accepted: " + JSON.stringify(said.slice(0, 60));
  const fold = panel.querySelector("details");
  if (!fold || fold.querySelector("summary").textContent.trim() !== "Read the agreement") return "The accepted agreement has no “Read the agreement”";
  const points = [...panel.querySelectorAll(".agreement-points li")];
  if (!points.length || points.some((li) => !fold.contains(li))) return "The accepted agreement's words aren't folded under “Read the agreement”";
  if (innerWidth >= 640 && fold.open) return "The accepted agreement is open before it's asked for";
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
// The notice beside allergen information is small and muted (Ray,
// 2026-11-15). Its rule had a selector that matched nothing, and nothing
// here recorded an allergen, so no page with the notice in view was looked
// at. The check records milk on the ingredient aged cheddar counts as.
const ALLERGEN_NOTICE = `(() => {
  const notice = [...document.querySelectorAll(".allergen-notice")].find((p) => p.getClientRects().length);
  if (!notice) return "The page shows no notice beside its allergen information";
  const style = getComputedStyle(notice);
  const muted = getComputedStyle(document.documentElement).getPropertyValue("--muted").trim();
  const probe = document.createElement("span");
  probe.style.color = muted;
  document.body.append(probe);
  const colour = getComputedStyle(probe).color;
  probe.remove();
  if (style.fontSize !== "14px" || style.color !== colour)
    return "The allergen notice is " + style.fontSize + " in " + style.color + ", not 14px in the muted colour";
  return "";
})()`;
// The ingredient hierarchy's words (Ray, 2026-11-15, for "Comes under"):
// cheddar counts as cheese, and cheese includes cheddar. A card with nothing
// to say isn't there, and nothing says "Nothing broader yet". The check
// puts Aged cheddar under another ingredient, so one page has each card.
const HIERARCHY = (has, hasnt, to = "/ingredients/") => `(() => {
  const main = document.querySelector("main");
  const old = /comes under|nothing broader|nothing narrower|what's under/i.exec(main.textContent);
  if (old) return 'The page still says "' + old[0] + '"';
  const cards = [...document.querySelectorAll(".ingredient-cards > div")];
  const card = (words) => cards.find((c) => c.querySelector("h2")?.textContent.trim() === words);
  for (const words of ${JSON.stringify(has)}) {
    if (!card(words)) return 'The page has no "' + words + '" card';
    if (!card(words).querySelector('a[href^="${to}"]')) return 'The "' + words + '" card links nothing under ${to}';
  }
  for (const words of ${JSON.stringify(hasnt)})
    if (card(words)) return 'The page has a "' + words + '" card with nothing to say';
  return "";
})()`;
// How many the list of ingredients found, as a sentence: it read "10
// ingredientsmatch" until this looked, the space lost with a template.
const COUNT_SAID = (words) => `(() => {
  const said = document.querySelector(".results-count")?.textContent.replace(/\\s+/g, " ").trim();
  return ${words}.test(said ?? "") ? "" : 'The count reads "' + said + '"';
})()`;
const COUNTS_AS = HIERARCHY(["Counts as"], ["Includes"]);
const INCLUDES = HIERARCHY(["Includes"], ["Counts as"]);
const NEITHER = HIERARCHY([], ["Counts as", "Includes"]);
// Equipment (Ray's spec, 2026-11-15). Ingredients and Equipment are a pair
// of tabs over each list, since the header has no room for a fifth section:
// two links, the page's own marked and its heading the same word, each 44px
// to tap; and the footer leads to Equipment from anywhere.
const CATALOG_TABS = (here) => `(() => {
  const nav = document.querySelector('main nav[aria-label="Ingredients and equipment"]');
  if (!nav) return "The list has no tabs for Ingredients and Equipment";
  const tabs = [...nav.querySelectorAll("a")];
  const words = tabs.map((a) => a.textContent.trim());
  if (words.join("|") !== "Ingredients|Equipment") return "The tabs read " + words.join(", ");
  const marked = tabs.filter((a) => a.getAttribute("aria-current") === "page").map((a) => a.textContent.trim());
  if (marked.join() !== ${JSON.stringify(here)}) return "The tab marked as this page is " + (marked.join() || "none") + ", not ${here}";
  const short = tabs.find((a) => a.getBoundingClientRect().height < 44);
  if (short) return "The " + short.textContent.trim() + " tab is " + Math.round(short.getBoundingClientRect().height) + "px to tap";
  const heading = document.querySelector("main h1")?.textContent.trim();
  if (heading !== ${JSON.stringify(here)}) return "Under the ${here} tab the heading is " + heading;
  if (!document.querySelector('footer a[href="/equipment"]')) return "The footer has no link to Equipment";
  return "";
})()`;
// The Equipment list is what a recipe can list. What any kitchen has is
// there only when asked for (the switch, or its name typed), and says so.
// A thing that counts as two says both, each a link. How many recipes
// need each is a column only once any does, and nothing here records a
// need yet: so no column, and no way to sort by it.
const EQUIPMENT_LIST = (assumed, atLeast = 50) => `(() => {
  const rows = [...document.querySelectorAll(".equipment-list tbody tr")];
  if (rows.length < ${atLeast}) return "The equipment list has " + rows.length + " rows";
  const said = (r) => r.textContent.replace(/\\s+/g, " ").trim();
  const any = rows.filter((r) => said(r).includes("Expected in any kitchen"));
  if (${assumed} !== any.length > 0) return any.length + " rows are of what any kitchen has";
  if (document.querySelector(".equipment-list .numeric, #equipment-sort")) return "The list counts recipes, or sorts by them, when none is recorded as needing anything";
  if (rows.length < 50) return "";
  const multi = rows.find((r) => r.querySelector("a.strong").textContent.trim() === "Multicooker");
  if (!multi) return "Multicooker isn't in the list";
  if (multi.querySelectorAll('.more a[href^="/equipment/"]').length !== 2 || !said(multi).includes("Counts as Pressure cooker and Slow cooker"))
    return "Multicooker's line reads “" + said(multi) + "”";
  return "";
})()`;
// What a piece of equipment's page says under its name.
const EQUIPMENT_SAYS = (words) => `(() => {
  const said = [...document.querySelectorAll(".equipment-page .status")].map((p) => p.textContent.replace(/\\s+/g, " ").trim());
  return said.includes(${JSON.stringify(words)}) ? "" : "The page says “" + said.join("” and “") + "”, not “${words}”";
})()`;
// A breadcrumb stops at the page's parent (Ray's round 5 list, item 4,
// 2026-11-15): its last part had been the page's own title, above the same
// words as the heading. On a phone it's one link back, with its chevron,
// on one line however long the parent's name, and still 44px to tap.
const CRUMBS = `(() => {
  const nav = document.querySelector("nav.crumbs");
  if (!nav) return "The page has no breadcrumb";
  // Each part is a link to somewhere else. The page's own title was the
  // one that wasn't a link. (Not by its words: a recipe may be named as
  // its book is, and the check's long one is.)
  const shown = [...nav.querySelectorAll("a, span:not([aria-hidden])")].filter((e) => e.getClientRects().length);
  if (!shown.length) return "The breadcrumb shows nothing";
  const here = shown.find((e) => e.tagName !== "A" || new URL(e.href).pathname === location.pathname);
  if (here) return 'The breadcrumb ends at the page itself ("' + here.textContent.trim().slice(0, 40) + '"), not its parent';
  if (!matchMedia("(max-width: 40rem)").matches) return "";
  if (shown.length !== 1 || shown[0].tagName !== "A")
    return "On a phone the breadcrumb shows " + shown.length + " parts, not the one link back";
  const height = Math.round(shown[0].getBoundingClientRect().height);
  if (height < 44 || height > 50) return "The link back is " + height + "px tall, not one line 44px to tap";
  if (!getComputedStyle(shown[0], "::before").content.includes("‹")) return "The link back has no chevron";
  return "";
})()`;
// The admin bar: its links in the bar on a wide screen; on a phone one row,
// with a button that says `label` (the admin page's name, or "This
// ingredient" on a page's own bar: Ray's round 5 list, item 5), and the
// links only once it's pressed, each then tall enough for a thumb.
const ADMIN_BAR = (label) => `(() => {
  const bar = document.querySelector("#admin-bar .admin-bar");
  if (!bar) return "the admin bar isn't shown";
  const button = bar.querySelector(".bar-toggle");
  if (!button) return "the admin bar has no button to fold its links under on a phone";
  const links = [...bar.querySelectorAll("a")].filter((a) => a.getClientRects().length);
  if (innerWidth >= 640)
    return links.length && !button.getClientRects().length ? "" : "the admin bar's links aren't in the bar on a wide screen";
  if (!button.textContent.includes(${JSON.stringify(label)}))
    return "the admin bar's button says " + JSON.stringify(button.textContent.trim()) + ", not " + ${JSON.stringify(JSON.stringify(label))};
  if (button.getAttribute("aria-expanded") === "true") {
    if (!links.length) return "the admin bar's button didn't open its links";
    const low = links.find((a) => a.getBoundingClientRect().height < 44);
    return low ? "the admin bar's link " + JSON.stringify(low.textContent.trim()) + " is " + Math.round(low.getBoundingClientRect().height) + "px tall, under 44px" : "";
  }
  if (links.length) return "the admin bar's links show on a phone before its button is pressed";
  const tall = Math.round(bar.getBoundingClientRect().height);
  if (tall > 56) return "the admin bar is " + tall + "px tall on a phone, more than one row";
  return "";
})()`;
const OPEN_HOW = `document.querySelector("main details.how").open = true`;
const OPEN_BAR = `document.querySelector(".bar-toggle").click()`;
// An author's bar offers the other author of the same name, to merge.
const DUPLICATE_SAID = `document.querySelector("#admin-bar").textContent.includes("Possible duplicate:") ? "" : "The author's admin bar doesn't offer the other author of that name"`;
// Saved recipes (Ray's round 5 list, item 6, 2026-11-15): a card has its
// tab's one move and "Remove", on one row; both are plain buttons, not
// toggles, named with the recipe; and on a phone a card whose title is one
// line is under 150px tall (it was 209px, with the two pills stacked).
const SAVED_CARDS = (move) => `(() => {
  const cards = [...document.querySelectorAll(".saved-page .hits .hit")].filter((c) => c.querySelector("h3") && c.querySelector("button"));
  if (!cards.length) return "Saved recipes shows no card with buttons";
  for (const card of cards) {
    const heading = card.querySelector("h3");
    const title = heading.textContent.trim();
    const buttons = [...card.querySelectorAll("button")];
    const words = buttons.map((b) => b.textContent.trim()).join(", ");
    if (words !== ${JSON.stringify(move + ", Remove")}) return "A saved recipe's buttons are " + JSON.stringify(words) + ", not " + ${JSON.stringify(JSON.stringify(move + ", Remove"))};
    const wrong = buttons.find((b) => b.hasAttribute("aria-pressed") || b.getAttribute("aria-label") !== b.textContent.trim() + ": " + title);
    if (wrong) return "A saved recipe's button " + JSON.stringify(wrong.textContent.trim()) + " is a toggle, or isn't named with its recipe";
    const middles = buttons.map((b) => b.getBoundingClientRect()).map((r) => r.top + r.height / 2);
    if (Math.abs(middles[0] - middles[1]) > 2) return "A saved recipe's two buttons aren't on one row";
    const lines = Math.round(heading.getBoundingClientRect().height / parseFloat(getComputedStyle(heading).lineHeight));
    const tall = Math.round(card.getBoundingClientRect().height);
    if (innerWidth < 640 && lines === 1 && tall >= 150) return "A saved recipe's card with a one-line title is " + tall + "px tall on a phone, not under 150px";
  }
  return "";
})()`;
// A list shared with you that you can't change has no buttons.
const SAVED_READ_ONLY = `document.querySelector(".saved-page .hits .hit") && !document.querySelector(".saved-page .hits button") ? "" : "A saved list that can't be changed shows no cards, or shows buttons"`;
// A click is only made on a phone (how.then), so what it should leave is
// only asked there.
const onPhone = (expect) => `innerWidth >= 640 ? "" : (${expect})`;
const OPEN_COOKED = `[...document.querySelectorAll(".saved-page .kind-filter button")].find((b) => b.textContent.trim().startsWith("Cooked")).click()`;
// Pressing a card's button, without the server being told: four browsers
// look at this page at once, in both themes, and a real press would move
// the recipe for all of them. The page changes itself first and isn't
// loaded again after, so what it shows is what a real press shows. And a
// wait of five seconds or more is over in a twentieth of one, so the line's
// eight seconds can be seen to pass: with focus on Undo they aren't
// counted, and the line is still there when axe has finished with it
// (Ray, 2026-11-15: the line stays while focus is on Undo); once focus
// has left, it goes.
const SAVED_PRESS = (words) => `(() => {
  const real = window.fetch;
  window.fetch = (url, init) =>
    init?.method && init.method !== "GET" && String(url).startsWith("/api/saved/")
      ? Promise.resolve(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }))
      : real(url, init);
  const later = window.setTimeout;
  window.setTimeout = (f, ms, ...rest) => later(f, ms >= 5000 ? 50 : ms, ...rest);
  [...document.querySelectorAll(".saved-page .hits .hit button")].find((b) => b.textContent.trim() === ${JSON.stringify(words)}).click();
})()`;
// And what it shows then: a line where the card was, with the same words
// in the live region, and focus on its Undo.
const SAVED_DONE = (words) => `(() => {
  const line = document.querySelector(".saved-page .done-line");
  if (!line) return "Saved recipes shows no line where the card was";
  if (line.innerText.trim() !== ${JSON.stringify(words + " Undo")}) return "The line where a saved recipe was says " + JSON.stringify(line.innerText.trim());
  const live = document.querySelector(".saved-page [aria-live]").textContent.trim();
  if (live !== ${JSON.stringify(words)}) return "The live region says " + JSON.stringify(live) + ", not the line's words";
  const focus = document.activeElement;
  if (!line.contains(focus) || focus.textContent.trim() !== "Undo") return "Focus isn't on Undo after a saved recipe's card goes";
  if (!(focus.getAttribute("aria-label") ?? "").startsWith("Undo: ")) return "Undo isn't named with its recipe";
  return "";
})()`;
// Focus taken off Undo, and the line's time left to pass: the line has
// gone, and the card it stood for hasn't come back.
const SAVED_LEAVE = `(async () => {
  // Once the page has put focus on Undo, which it does after it has drawn
  // the line.
  await new Promise((r) => setTimeout(r, 100));
  const cards = document.querySelectorAll(".saved-page .hits .hit").length;
  if (document.activeElement.textContent.trim() !== "Undo") throw new Error("Focus isn't on Undo to take off it");
  document.activeElement.blur();
  await new Promise((r) => setTimeout(r, 400));
  window.cardsWithLine = cards;
})()`;
const SAVED_GONE = `(() => {
  if (document.querySelector(".saved-page .done-line")) return "The line where a saved recipe was is still there after focus left Undo";
  const cards = document.querySelectorAll(".saved-page .hits .hit").length;
  return cards === window.cardsWithLine - 1 ? "" : "With the line gone there are " + cards + " cards, not one fewer than the " + window.cardsWithLine + " with it";
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
// Search's filters (Ray's round 5 list, item 9, 2026-11-15: "Filters
// probably makes sense under More options"). On a phone they are inside
// that panel and not a landmark, and above the results there is one button
// that opens anything, before a search and after. On a wide screen they
// are the rail beside the results, a landmark called "Filters", as before.
const FILTERS_IN_MORE = `(() => {
  const results = document.querySelector("#results");
  const panel = document.querySelector("#search-more");
  const filters = document.querySelector("main .filters");
  if (!filters || !filters.querySelector("input[type=checkbox]")) return "Search has no filters";
  if (!matchMedia("(max-width: 40rem)").matches)
    return filters.tagName === "ASIDE" && filters.getAttribute("aria-label") === "Filters" && !panel.contains(filters)
      ? ""
      : "On a wide screen the filters aren't the rail beside the results";
  if (!panel.contains(filters)) return "On a phone the filters aren't inside “More options”";
  if (filters.tagName === "ASIDE" || filters.hasAttribute("aria-label") || document.querySelector("main aside")) return "On a phone the filters are still a landmark";
  const openers = [...document.querySelectorAll("main [aria-expanded], main summary")].filter(
    (e) => e.getClientRects().length && !panel.contains(e) && e.compareDocumentPosition(results) & Node.DOCUMENT_POSITION_FOLLOWING,
  );
  if (openers.length !== 1 || !openers[0].textContent.trim().startsWith("More options"))
    return "On a phone " + openers.length + " things open something above the results (" + openers.map((e) => e.textContent.trim()).join(", ") + "), not “More options” alone";
  if (openers[0].getAttribute("aria-controls") !== panel.id) return "“More options” doesn't say which panel it opens";
  const title = panel.querySelector("h2");
  if (title?.textContent.trim() !== "Filters" || !(title.compareDocumentPosition(filters) & Node.DOCUMENT_POSITION_FOLLOWING)) return "In “More options” the filters have no “Filters” heading over them";
  return "";
})()`;
// A link that arrives with a filter set: on a phone "More options" is open
// and counts it, with its box ticked inside; on a wide screen the panel
// stays shut and counts nothing, the filter being in the rail. Either way
// it is among the filters in use, above the results.
const FILTER_ARRIVED = `(() => {
  const more = document.querySelector(".more-toggle");
  const narrow = matchMedia("(max-width: 40rem)").matches;
  const words = more.textContent.trim();
  const ticked = [...document.querySelectorAll("main .filters input:checked")].filter((i) => i.getClientRects().length);
  if (!ticked.some((i) => i.closest("label").textContent.trim() === "Vegetarian")) return "The link's filter isn't shown ticked";
  if (![...document.querySelectorAll(".filter-chip")].some((c) => c.textContent.trim() === "Vegetarian")) return "The link's filter isn't among the filters in use";
  if (narrow) return more.getAttribute("aria-expanded") === "true" && words === "More options (1)" ? "" : "On a phone a link with a filter leaves “More options” " + (more.getAttribute("aria-expanded") === "true" ? "open" : "shut") + ", saying " + JSON.stringify(words);
  return more.getAttribute("aria-expanded") === "false" && words === "More options" ? "" : "On a wide screen a link with a filter has “More options” saying " + JSON.stringify(words);
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
  // It names a recipe the book hasn't got, so it's flagged: Flagged
  // recipes was wider than a tablet with a title this long in it (Ray's
  // round 5 list, 2b), and had only a short one to show here.
  const slow = await recipe("Slow-Roasted Aged Cheddar and Caramelised Onion Biscuits with Brown Butter", "30", [
    "Aged cheddar",
    "Onion",
    "Shortcrust pastry (p. 98)",
  ]);
  const ids = await api("/api/ingredients?q=cheddar", "admin");
  const cheddar = ids.ingredients.find((i) => i.name === "Aged cheddar").id;
  const cheese = (await api("/api/ingredients?q=butter", "admin")).ingredients[0].id;
  await api(`/api/ingredients/${cheddar}/parent`, "admin", { parent: cheese }, "PUT");
  // And it contains milk, so its page, aged cheddar's and a recipe's with
  // either have allergen information, and the notice beside it.
  await api(`/api/ingredients/${cheese}/allergens`, "admin", { statuses: { milk: "contains" } }, "PUT");

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
  // And a click on a book with a title of many ordinary words, which is
  // what a real one has: Buy-link clicks kept such a title on one line and
  // was wider than a tablet (Ray's round 5 list, 2c).
  const windy = await api("/api/sources/manual", "admin", {
    title: "The Long Way Round the Kitchen: Three Hundred Unhurried Recipes for Cold Evenings and Slow Weekends",
    authors: ["Ann Author"],
    year: 2021,
    isbn: "9780393541151",
  });
  const windyEdition = (await api(`/api/sources/${windy.id}`, "admin")).editions[0].id;
  const windyClick = await fetch(`${BASE}/go/bookshop/${windyEdition}?from=/sources/${windy.id}`, {
    redirect: "manual",
    headers: { "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36" },
  });
  if (windyClick.status < 300 || windyClick.status >= 400)
    throw new Error(`The buy link answered ${windyClick.status}`);
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
  // A recipe in each of the two books users.sql gives a picture, for the
  // thumbnail beside a recipe in a list.
  for (const title of ["Picture on the Cover", "Picture That Never Came"]) {
    const pictured = (await api(`/api/sources?q=${encodeURIComponent(title)}`, "admin")).sources.find(
      (b) => b.title === title,
    );
    const picturedEdition = (await api(`/api/sources/${pictured.id}`, "admin")).editions[0].id;
    await api(`/api/sources/${pictured.id}/recipes`, "admin", {
      title: `Thumbnail Toast, ${title}`,
      editions: [{ edition_id: picturedEdition, page: "1" }],
      ingredients: ["Bread", "Butter"],
    });
  }
  const wordyAuthor = wordyPage.credits[0].author_id;
  // A second author named as Ann Author is, and a second named the long
  // word, so each one's page offers the other to merge in its admin bar:
  // the bar's longest state, and the one with a typed name in it. A name
  // that's already an author's means that author, so each is made under
  // another name and then renamed, which nothing refuses. Last, so that
  // nothing after it credits "Ann Author" and gets a third.
  for (const [title, name] of [
    ["The Other Ann's Book", "Ann Author"],
    ["The Other Long Book", LONG],
  ]) {
    const twinBook = await api("/api/sources/manual", "admin", { title, authors: [`${title}'s author`] });
    const twin = (await api(`/api/sources/${twinBook.id}`, "admin")).credits[0].author_id;
    await api(`/api/authors/${twin}`, "admin", { name, kind: "person" }, "PATCH");
  }
  // The ingredient users.sql suggests links for, and has foods like.
  const oats = (await api("/api/ingredients?q=Quick-Cooking Oats", "admin")).ingredients.find(
    (i) => i.name === "Quick-Cooking Oats",
  ).id;
  const wordyIngredient = (await api(`/api/recipes/${word.id}`, "admin")).lines
    .flatMap((l) => l.options)
    .find((o) => o.ingredient?.name.toLowerCase() === LONG.toLowerCase()).ingredient.id;
  // The equipment list is there from the start (migration 0079): one thing
  // that counts as two others, one that includes it, one with nothing to
  // say, and one any kitchen has.
  const kit = (await api("/api/equipment?assumed=true", "admin")).equipment;
  const [multicooker, slowCooker, wok, stovetop] = ["Multicooker", "Slow cooker", "Wok", "Stovetop"].map(
    (name) => kit.find((e) => e.name === name).id,
  );
  return { long, oats, wordy, word, wordyAuthor, wordyIngredient, waiting: waiting.id, vegetarian, book, blend, biscuits, site, web, magazine, issue, show, episode, box, pie, group, author, cheddar, cheese, multicooker, slowCooker, wok, stovetop };
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
    ["/search", null, { expect: FILTERS_IN_MORE }],
    [`/search?i=${s.cheddar}`, null],
    ["/search?q=biscuits", null, { expect: `(${THUMBS_DRAWN}) || (${FILTERS_IN_MORE})` }],
    ["/search?q=thumbnail+toast", null, { expect: `(${THUMBS_DRAWN}) || (${THUMB_PICTURES})` }],
    ["/search?q=biscuits&kind=book&kind=website", null],
    [`/search?tag=${s.vegetarian}`, null, { expect: `(${FILTERS_IN_MORE}) || (${FILTER_ARRIVED})` }],
    [`/search?q=biscuits&x=${s.cheddar}`, null, { expect: OLD_LINK }],
    ["/sources", null, { expect: COVERS_SHOWN }],
    ["/sources", "cook"],
    ["/sources", "admin"],
    ["/sources?kind=book&kind=website&sort=recipes", null],
    [`/sources/${s.book.id}`, null, { expect: `(${TOP_RATED_SHOWN}) || (${CRUMBS}) || (${BUY_BY_FORMAT}) || (${BUY_OUTLINED})` }],
    [`/sources/${s.book.id}`, "admin", { expect: ADMIN_BAR("This book") }],
    [`/sources/${s.site.id}`, null],
    [`/sources/${s.magazine.id}`, null],
    [`/sources/${s.show.id}`, null],
    [`/sources/${s.box.id}`, "cook"],
    [`/sources/${s.book.id}/edit`, "admin"],
    [`/sources/${s.book.id}/recipes/new`, "admin"],
    [`/sources/${s.show.id}/recipes/new`, "admin"],
    [`/sources/${s.box.id}/recipes/new`, "cook"],
    [`/sources/${s.book.id}/bulk`, "admin"],
    [`/recipes/${s.biscuits.id}`, null, { expect: `(${CRUMBS}) || (${BUY_OUTLINED})` }],
    [`/recipes/${s.biscuits.id}`, "admin"],
    [`/recipes/${s.web.id}`, null],
    [`/recipes/${s.issue.id}`, null],
    [`/recipes/${s.episode.id}`, null],
    [`/recipes/${s.pie.id}`, "cook"],
    [`/recipes/${s.biscuits.id}/edit`, "admin"],
    ["/ingredients", null, { expect: CATALOG_TABS("Ingredients") }],
    ["/ingredients?top=true&sort=name", null, { expect: COUNT_SAID("/^\\d+ main ingredients\\.$/") }],
    ["/ingredients?q=cheddar", null, { expect: COUNT_SAID("/^1 ingredient matches “cheddar”\\.$/") }],
    [`/ingredients/${s.cheddar}`, null, { expect: `(${COUNTS_AS}) || (${CRUMBS})` }],
    [`/ingredients/${s.cheddar}`, "admin", { expect: `(${COUNTS_AS}) || (${ADMIN_BAR("This ingredient")})` }],
    [`/ingredients/${s.cheese}`, null, { expect: `(${INCLUDES}) || (${ALLERGEN_NOTICE})` }],
    ["/equipment", null, { phone: true, expect: `(${CATALOG_TABS("Equipment")}) || (${EQUIPMENT_LIST(false)}) || (${COUNT_SAID("/^\\d+ pieces of equipment\\.$/")})` }],
    ["/equipment?assumed=true&sort=name", null, { phone: true, expect: EQUIPMENT_LIST(true) }],
    ["/equipment?q=frying+pan", null, { expect: `(${EQUIPMENT_LIST(true, 1)}) || (${COUNT_SAID("/^1 piece of equipment matches “frying pan”\\.$/")})` }],
    ["/equipment?q=no+such+thing", null],
    [`/equipment/${s.multicooker}`, null, { expect: `(${HIERARCHY(["Counts as"], ["Includes"], "/equipment/")}) || (${CRUMBS}) || (${EQUIPMENT_SAYS("No recipe lists it yet.")})` }],
    [`/equipment/${s.slowCooker}`, null, { expect: HIERARCHY(["Includes"], ["Counts as", "Also called"], "/equipment/") }],
    [`/equipment/${s.wok}`, null, { expect: `(${HIERARCHY([], ["Counts as", "Includes", "Also called"], "/equipment/")}) || (${EQUIPMENT_SAYS("Nothing it counts as, includes or is also called yet.")})` }],
    [`/equipment/${s.stovetop}`, null, { expect: EQUIPMENT_SAYS("Expected in any kitchen, so recipes don't list it.") }],
    ["/authors", null],
    ["/authors?sort=recipes&kind=person", null],
    [`/authors/${s.author}`, null, { expect: `(${TOP_RATED_SHOWN}) || (${CRUMBS})` }],
    [`/authors/${s.author}`, "admin", { expect: ADMIN_BAR("This author") }],
    ["/groups", "cook"],
    [`/groups/${s.group.id}`, "cook", { expect: CRUMBS }],
    ["/invite/not-a-real-invite", null],
    ["/account", "cook", { expect: AGREEMENT_FOLDED }],
    ["/account", "cook", { phone: true, then: `document.querySelector(".agreement-panel details").open = true`, expect: AGREEMENT_FOLDED }],
    ["/account/flags", "admin"],
    ["/admin", "admin"],
    ["/admin/flags", "admin", { expect: ADMIN_BAR("Flagged recipes") }],
    ["/admin/imports", "admin"],
    ["/admin/suggestions", "admin"],
    ["/admin/api", "admin"],
    ["/admin/clicks", "admin", { expect: CRUMBS }],
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
    [`/recipes/${s.biscuits.id}`, "cook", { expect: ALLERGEN_NOTICE }],
    ["/account", "admin", { expect: AGREEMENT_FOLDED }],
    ["/requests", null],
    ["/requests", "cook"],
    ["/admin/suggestions", "cook"],
    ["/data", null],
    ["/larder", "cook", { expect: HOW_FOLDED(false) }],
    ["/larder", "admin"],
    ["/search?larder=1", "cook"],
    ["/larder", null, { expect: HOW_FOLDED(true) }],
    ["/shelf", "cook", { phone: true, expect: `(${WANTS_ON_SHELF}) || (${HOW_FOLDED(false)})` }],
    ["/shelf", "admin", { phone: true, expect: WANTS_ON_SHELF }],
    ["/shelf", null, { phone: true, expect: HOW_FOLDED(true) }],
    // The book Cy wants: its shops first, on a phone.
    [`/sources/${s.long.id}`, "cook", { phone: true, expect: `(${WANTED_BOOK}) || (${BUY_BY_FORMAT})` }],
    ["/saved", "cook", { expect: `(${THUMBS_DRAWN}) || (${SAVED_CARDS("Cooked it")}) || (${HOW_FOLDED(false)})` }],
    ["/saved", "admin", { expect: SAVED_READ_ONLY }],
    // Its other tab, and a card's two buttons pressed, each of which leaves
    // a line with Undo where the card was.
    ["/saved", "cook", { phone: true, then: OPEN_COOKED, expect: onPhone(SAVED_CARDS("Cook again")) }],
    ["/saved", "cook", { phone: true, then: SAVED_PRESS("Cooked it"), expect: onPhone(SAVED_DONE("Moved to Cooked.")) }],
    ["/saved", "cook", { phone: true, then: SAVED_PRESS("Remove"), expect: onPhone(SAVED_DONE("Removed.")) }],
    [
      "/saved",
      "cook",
      { phone: true, then: `${SAVED_PRESS("Cooked it")}; ${SAVED_LEAVE}`, expect: onPhone(SAVED_GONE) },
    ],
    ["/saved", null, { expect: HOW_FOLDED(true) }],
    // "How this works" opened by hand on each, on a phone.
    ["/shelf", "cook", { phone: true, then: OPEN_HOW }],
    ["/larder", "cook", { phone: true, then: OPEN_HOW }],
    ["/saved", "cook", { phone: true, then: OPEN_HOW }],
    ["/saved#notes", "cook", { expect: THUMBS_DRAWN }],
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
      { phone: true, then: OPEN_BAR, expect: ADMIN_BAR("Flagged recipes") },
    ],
    // And the bars an ingredient's, a source's and an author's page add for
    // themselves, opened: an ingredient with recipes, so "Delete" is a
    // sentence and not a link, and two authors with a second of their name
    // to merge, one of them the long word.
    [`/ingredients/${s.cheddar}`, "admin", { phone: true, then: OPEN_BAR, expect: ADMIN_BAR("This ingredient") }],
    [`/sources/${s.book.id}`, "admin", { phone: true, then: OPEN_BAR, expect: ADMIN_BAR("This book") }],
    [`/authors/${s.author}`, "admin", { phone: true, then: OPEN_BAR, expect: `(${ADMIN_BAR("This author")}) || (${DUPLICATE_SAID})` }],
    [`/authors/${s.wordyAuthor}`, "admin", { phone: true, then: OPEN_BAR, expect: `(${ADMIN_BAR("This author")}) || (${DUPLICATE_SAID})` }],
    [
      "/admin/suggestions",
      "admin",
      { phone: true, then: OPEN_HOW },
    ],
    // Search: "More options" opened, signed out and with a larder, which
    // on a phone has the filters in it; opened by a link with a filter set;
    // and kept to what can be made now, with recipes to list and with none.
    ["/search", null, { phone: true, then: `document.querySelector(".more-toggle").click()` }],
    ["/search?larder=1", "cook", { phone: true, then: `document.querySelector(".more-toggle").click()` }],
    [`/search?tag=${s.vegetarian}`, null, { phone: true, expect: FILTER_ARRIVED }],
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
    [`/recipes/${s.word.id}`, null, { expect: CRUMBS }],
    [`/recipes/${s.word.id}`, "admin"],
    [`/recipes/${s.word.id}`, "cook"],
    [`/recipes/${s.word.id}/edit`, "admin"],
    [`/authors/${s.wordyAuthor}`, null],
    [`/authors/${s.wordyAuthor}`, "admin"],
    [`/ingredients/${s.wordyIngredient}`, null, { expect: NEITHER }],
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
  // The page has the window's focus, as it does in front of a person. A
  // headless browser's has none, and then no element is sent a focus or a
  // blur event whatever is focused: the Undo line on Saved recipes, which
  // waits for focus to leave it, never saw it leave (2026-11-15).
  await send("Emulation.setFocusEmulationEnabled", { enabled: true });
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
    `document.querySelector("main").insertAdjacentHTML("beforeend", '<p style="color:#ccc;background:#fff">faint</p><img src="/x.png"><div style="width:${PHONE + 20}px">wide</div><p style="width:2rem">Breakfast</p><table><tr><td style="width:4rem">a title of a good many words in a column left no room</td></tr></table>')`,
  );
  const found = (await runAxe(b)).violations.map((v) => v.id);
  const wide = await overflowOf(b, PHONE);
  const missed = ["color-contrast", "image-alt"].filter((id) => !found.includes(id));
  if (wide <= 0) missed.push("overflow");
  if (!(await b.evaluate(BROKEN_WORDS)).some((w) => w.startsWith('"Breakfast"'))) missed.push("a broken word");
  if (!(await b.evaluate(SQUEEZED_CELLS)).some((c) => c.startsWith('"a title of a good many words'))) missed.push("a squeezed cell");
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
  // (Not between a phone and a desktop: those views are for layout, and
  // are signed in whoever the entry was written for.)
  const between = BETWEEN.includes(width);
  if (how.expect && !between) {
    const wrong = await b.evaluate(how.expect);
    if (wrong) problems.push(wrong);
  }
  const overflow = await overflowOf(b, width);
  if (overflow > 0) problems.push(`scrolls sideways by ${overflow}px at ${width}px wide`);
  for (const word of await b.evaluate(BROKEN_WORDS)) problems.push(`breaks ${word} in two`);
  for (const cell of await b.evaluate(SQUEEZED_CELLS)) problems.push(`squeezes a table: ${cell}`);
  // axe once per theme and page, at desktop width; the phone pass is for
  // layout, unless the page shows a phone something of its own.
  if (!between && (width >= 600 || how.phone)) {
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
// Between the two, each page once at each width, signed in: as Cy where the
// entry is signed out or his, as Ada where only she may see it.
const middle = new Map(
  pages(s).map(([path, who]) => [`${path} ${who ?? "cook"}`, { path, who: who ?? "cook" }]),
);
for (const { path, who } of middle.values())
  for (const width of BETWEEN) views.push({ path, who, theme: "light", width, how: {} });
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
  `${checked} page views checked (axe at 1280px, and at ${PHONE}px where a phone has its own; layout at ${PHONE}px, as a touch screen, and signed in at ${BETWEEN.join(", ")}px), ${failed} with problems.`,
);
process.exit(failed ? 1 : 0);
