// Accessibility check: every kind of page, as the built app serves it, run
// through axe-core's WCAG 2.1 A and AA rules (contrast among them) in the
// light and dark themes, and checked for sideways scrolling at phone width.
// Ray, 2026-11-08: "make sure we're passing accessibility checks, contrast,
// etc. along the way".
//
// It adds what it looks at through the API, as the people users.sql plants,
// so run it against a throwaway database only, with
// OPENLARDER_ARCHIVE_WEB_PAGES=false so web recipes ask the Internet Archive
// for nothing:
//
//   psql "$DATABASE" -f a11y/users.sql
//   node a11y/check.mjs                 # A11Y_BASE, CHROME to override
//
// What axe can't judge (whether wording is clear, whether focus order makes
// sense, how a screen reader actually sounds) still needs a person.

import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
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
  await recipe("Slow-Roasted Aged Cheddar and Caramelised Onion Biscuits with Brown Butter", "30", [
    "Aged cheddar",
    "Onion",
  ]);
  const ids = await api("/api/ingredients?q=cheddar", "admin");
  const cheddar = ids.ingredients.find((i) => i.name === "Aged cheddar").id;
  const cheese = (await api("/api/ingredients?q=butter", "admin")).ingredients[0].id;
  await api(`/api/ingredients/${cheddar}/parent`, "admin", { parent: cheese }, "PUT");

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
    if (n === 1) await api(`/api/recipes/${bake.id}/rating`, "cook", { spoons: 5 }, "PUT");
  }
  return { long, waiting: waiting.id, vegetarian, book, blend, biscuits, site, web, magazine, issue, show, episode, box, pie, group, author, cheddar };
}

function pages(s) {
  // [path, who, how]: who is signed in, or nobody. how.phone: axe at the
  // phone's width too, for a page that shows a phone something of its
  // own; how.then: script to run there first, for a state a click makes.
  return [
    ["/", null],
    ["/", "admin"],
    ["/search", null],
    [`/search?i=${s.cheddar}`, null],
    ["/search?q=biscuits", null],
    ["/search?q=biscuits&kind=book&kind=website", null],
    [`/search?tag=${s.vegetarian}`, null],
    [`/search?q=biscuits&x=${s.cheddar}`, null],
    ["/sources", null],
    ["/sources", "cook"],
    ["/sources", "admin"],
    ["/sources?kind=book&kind=website&sort=recipes", null],
    [`/sources/${s.book.id}`, null],
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
    [`/authors/${s.author}`, null],
    [`/authors/${s.author}`, "admin"],
    ["/groups", "cook"],
    [`/groups/${s.group.id}`, "cook"],
    ["/invite/not-a-real-invite", null],
    ["/account", "cook"],
    ["/account/flags", "admin"],
    ["/admin", "admin"],
    ["/admin/flags", "admin"],
    ["/admin/imports", "admin"],
    ["/admin/suggestions", "admin"],
    ["/admin/api", "admin"],
    ["/admin/clicks", "admin"],
    ["/admin/merges", "admin"],
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
    ["/shelf", "cook"],
    ["/shelf", "admin"],
    ["/shelf", null],
    ["/saved", "cook"],
    ["/saved", "admin"],
    ["/saved", null],
    ["/saved#notes", "cook"],
    ["/saved#notes", "admin"],
    ["/search?sv=1", "cook"],
    [`/sources/${s.book.id}`, "cook"],
    ["/search?own=1&q=biscuit", "cook"],
    ["/privacy", null],
    ["/terms", null],
    ["/welcome", "new"],
    ["/sign-in-failed", null],
    // A long book: on a phone its parts are in another order, with the
    // first thirty recipes; then with all of them shown.
    [`/sources/${s.long.id}`, null, { phone: true }],
    [
      `/sources/${s.long.id}`,
      "cook",
      { phone: true, then: `document.querySelector(".show-all button").click()` },
    ],
  ];
}

// Chrome over the DevTools protocol, as the render checks drive it.
async function browser() {
  const port = 9400 + Math.floor(Math.random() * 400);
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
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) {
      pending.get(m.id)(m);
      pending.delete(m.id);
    }
    if (m.method === "Runtime.exceptionThrown")
      failures.push(m.params.exceptionDetails?.exception?.description?.split("\n")[0]);
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
  await send("Runtime.enable");
  return { send, evaluate, failures, close: () => (ws.close(), proc.kill()) };
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
  await b.send("Emulation.setDeviceMetricsOverride", {
    width: 390,
    height: 900,
    deviceScaleFactor: 1,
    mobile: true,
  });
  await b.send("Page.navigate", { url: `${BASE}/privacy` });
  await sleep(2000);
  await b.evaluate(
    `document.querySelector("main").insertAdjacentHTML("beforeend", '<p style="color:#ccc;background:#fff">faint</p><img src="/x.png"><div style="width:500px">wide</div>')`,
  );
  const found = (await runAxe(b)).violations.map((v) => v.id);
  const wide = await overflowOf(b, 390);
  const missed = ["color-contrast", "image-alt"].filter((id) => !found.includes(id));
  if (missed.length || wide <= 0)
    throw new Error(
      `The control wasn't caught (missed ${missed.join(", ") || "overflow"}); the check proves nothing.`,
    );
}

const undecided = new Map();

async function check(b, path, who, theme, width, how = {}) {
  await b.send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-color-scheme", value: theme }],
  });
  await b.send("Emulation.setDeviceMetricsOverride", {
    width,
    height: 900,
    deviceScaleFactor: 1,
    mobile: width < 600,
  });
  await b.send("Network.clearBrowserCookies");
  if (who)
    await b.send("Network.setCookie", {
      name: "openlarder_session",
      value: TOKENS[who],
      url: `${BASE}/`,
      httpOnly: true,
    });
  await b.send("Page.navigate", { url: `${BASE}${path}` });
  // Pages load their data after they're drawn; wait for "Loading…" to go,
  // and for a recipe's ingredient lines to be checked.
  for (let i = 0; i < 40; i++) {
    await sleep(250);
    const busy = await b.evaluate(
      `document.readyState !== "complete" || /Loading…/.test(document.querySelector("main")?.innerText ?? "")` +
        ` || (!!document.querySelector(".line-row input:not(:placeholder-shown)") && !document.querySelector(".line-tag"))`,
    );
    if (!busy && i > 3) break;
  }
  if (how.then && width < 600) {
    await b.evaluate(how.then);
    await sleep(500);
  }
  const problems = [];
  const overflow = await overflowOf(b, width);
  if (overflow > 0) problems.push(`scrolls sideways by ${overflow}px at ${width}px wide`);
  // axe once per theme and page, at desktop width; the phone pass is for
  // layout, unless the page shows a phone something of its own.
  if (width >= 600 || how.phone) {
    const { violations, incomplete } = await runAxe(b);
    for (const v of violations)
      problems.push(`${v.id} (${v.impact}): ${v.help}\n      ${v.nodes.join("\n      ")}`);
    for (const v of incomplete)
      for (const node of v.nodes)
        undecided.set(`${v.id}: ${path} (${theme}) ${node}`, true);
  }
  return problems;
}

const s = await seed();
const b = await browser();
let failed = 0;
let checked = 0;
try {
  await control(b);
  for (const theme of ["light", "dark"]) {
    for (const [path, who, how] of pages(s)) {
      for (const width of [1280, 390]) {
        const problems = await check(b, path, who, theme, width, how);
        checked++;
        if (problems.length) {
          failed++;
          console.log(`✗ ${path} (${who ?? "signed out"}, ${theme}, ${width}px)`);
          for (const p of problems) console.log(`    ${p}`);
        }
      }
    }
  }
  for (const f of b.failures) {
    failed++;
    console.log(`✗ script error: ${f}`);
  }
} finally {
  b.close();
}
if (undecided.size) {
  console.log("For a person to look at, where axe couldn't decide:");
  for (const where of undecided.keys()) console.log(`    ${where}`);
}
console.log(
  `${checked} page views checked (axe at 1280px, and at 390px where a phone has its own; layout at 390px), ${failed} with problems.`,
);
process.exit(failed ? 1 : 0);
