// OpenLarder's service worker. It does two things, and nothing else.
//
// 1. A page of the site's own for when there's no connection
//    (/offline.html), where the browser would show its error. *Ray,
//    2026-11-17: the installable web app.* Opened from its icon with no
//    signal, an app that shows the browser's error page looks broken.
//
// 2. On a device where someone has switched it on (Account, "This device"),
//    a copy of what is theirs, to read with no connection: their larder,
//    shelf, equipment and saved recipes. *Ray, 2026-11-17, asked where a
//    copy may be kept: "only where switched on".* Off to begin with, on
//    every device, so nothing of anyone's is on a shared computer unless
//    they chose that there.
//
// Everything else goes to the network exactly as if this weren't here. On a
// device whose switch is off, only a page being opened passes through it.
//
// What is kept (YOURS), and for whom. The copy is one person's: who they
// are is asked of the server when it's switched on and kept beside it
// (OWNER). It is the four pages (PAGES, all the same page of the site's),
// what they ask the server for (DATA) and what the page is drawn with
// (PARTS). Each is fetched from the network every time, and a copy kept as
// it comes; the copy answers only when the network doesn't.
//
// When it goes, all of it at once (forget):
// - the switch is turned off;
// - signing out, or deleting the account, by the site's own forms: before
//   the request leaves;
// - the server says nobody is signed in (401), or that someone else is;
// - a copy is asked for when the server last said its owner was signed in
//   longer ago than OLDEST, the length of a session: a device that hasn't
//   been online for that long is signed out in all but the knowing of it.
// A private collection must never leak, and a copy on a phone someone else
// picks up is a leak. What this can't do: take a copy off a device that
// never comes online again before OLDEST is up.
//
// Changing it: a browser fetches this file again on its own (main.py sends
// it no-cache, so Cloudflare keeps no old one) and the new one takes over
// at once. To be rid of it, ship one whose "activate" calls
// self.registration.unregister(); deleting the file leaves the old one
// running in every browser that has it.

// A new name when the page kept must be fetched again; the old is deleted.
const KEPT = "openlarder-offline-v2";
const OFFLINE = "/offline.html";

// There only while this device's switch is on. web/src/offline.ts and
// offline.html look for it by this name.
const YOURS = "openlarder-yours-v1";
const PAGES = ["/larder", "/shelf", "/equipment/mine", "/saved"];
const DATA = [
  "/api/auth/me",
  "/api/site",
  "/api/larder",
  "/api/shelf",
  "/api/equipment-lists",
  "/api/saved",
  "/api/notes",
];
// The build's script and stylesheet, the fonts, and the pictures in the
// header and the tab.
const PARTS =
  /^\/(assets|fonts)\/[\w.-]+$|^\/(logo-light\.svg|logo-dark\.svg|favicon\.svg|favicon\.ico|site\.webmanifest|icon-192\.png)$/;
// Where the page and its owner are kept: addresses the site hasn't got.
const SHELL = "/__kept/page";
const OWNER = "/__kept/owner";
const AT = "X-Kept-At";
const OLDEST = 30 * 24 * 60 * 60 * 1000;
// What ends a session by the site's own forms.
const LEAVING = ["/api/auth/logout", "/api/account/delete"];

// Whether this device's switch is on, as far as is known: asked once as the
// worker starts, and a page being opened waits for the answer, so whatever
// that page then asks for is answered knowing it.
let on = false;
const known = caches.has(YOURS).then((there) => {
  on = there;
});

async function yours() {
  return (await caches.has(YOURS)) ? caches.open(YOURS) : null;
}

async function forget() {
  on = false;
  await caches.delete(YOURS);
}

// A response kept as it came, with when.
async function keep(cache, key, response) {
  const headers = new Headers(response.headers);
  headers.set(AT, String(Date.now()));
  await cache.put(
    key,
    new Response(await response.blob(), { status: response.status, headers }),
  );
}

// Whose the copy is, and when the server last said they were signed in.
async function owner(cache) {
  return (await cache.match(OWNER))?.json().catch(() => null);
}

async function own(cache, id) {
  await cache.put(
    OWNER,
    new Response(JSON.stringify({ id, at: Date.now() }), {
      headers: { "Content-Type": "application/json" },
    }),
  );
}

// A copy to answer with and when it was kept, or nothing. Asked for when
// its owner was last known to be signed in longer ago than OLDEST, it and
// everything with it goes.
async function copy(key) {
  const cache = await yours();
  if (!cache) return null;
  const whose = await owner(cache);
  if (!whose?.id || !(Date.now() - whose.at <= OLDEST)) {
    await forget();
    return null;
  }
  const found = await cache.match(key);
  return found ? { response: found, at: Number(found.headers.get(AT)) || whose.at } : null;
}

// One script and one stylesheet are kept: a new build's take the place of
// the last one's. (The build is one of each. If it comes to be several,
// this keeps only the latest of each kind, and a page drawn from the copy
// would lack the rest.)
async function prune(cache, path) {
  const kind = path.match(/^\/assets\/.*(\.[a-z0-9]+)$/)?.[1];
  if (!kind) return;
  for (const request of await cache.keys()) {
    const other = new URL(request.url).pathname;
    if (other !== path && other.startsWith("/assets/") && other.endsWith(kind))
      await cache.delete(request);
  }
}

// What the server just said, taken into the copy; or the copy let go,
// where it says the copy is nobody's now.
async function settle(path, response) {
  const cache = await yours();
  if (!cache) return;
  if (response.status === 401) return forget();
  if (!response.ok) return;
  if (path === "/api/auth/me") {
    const me = await response
      .clone()
      .json()
      .catch(() => null);
    const whose = await owner(cache);
    if (!me?.id || me.id !== whose?.id) return forget();
    await own(cache, me.id);
  }
  // What the page is drawn with doesn't change under its name: kept once.
  if (!DATA.includes(path) && (await cache.match(path))) return;
  await keep(cache, path, response);
  await prune(cache, path);
}

// The page that asked is told its answer came from the copy, and how old
// that is, so it can say so.
async function tell(clientId, at) {
  const client = clientId && (await self.clients.get(clientId));
  if (client) client.postMessage({ type: "kept", at });
}

// Something a kept page asks for or is drawn with: from the network, and
// the copy brought up to date; from the copy when the network doesn't
// answer. With neither, it fails as it would have.
async function part(event, path) {
  let response;
  try {
    response = await fetch(event.request);
  } catch (failed) {
    const kept = await copy(path);
    if (!kept) throw failed;
    if (DATA.includes(path)) await tell(event.clientId, kept.at);
    return kept.response;
  }
  await settle(path, response.clone());
  return response;
}

// A page being opened.
async function page(event, path) {
  await known;
  try {
    const response = (await event.preloadResponse) || (await fetch(event.request));
    if (on && response.ok && PAGES.includes(path)) {
      const cache = await yours();
      if (cache) await keep(cache, SHELL, response.clone());
    }
    return response;
  } catch {
    // No answer at all: no connection, or no server. An answer that is
    // an error is the server's to give, and was returned above.
    if (PAGES.includes(path)) {
      const kept = await copy(SHELL);
      if (kept) return kept.response;
    }
    return (await caches.match(OFFLINE)) || Response.error();
  }
}

// The switch turned on: who is signed in is asked of the server, and
// everything the four pages need is fetched and kept for them. All of it
// or none: a copy with a page missing would fail someone in a shop.
async function start({ user, parts }) {
  const asked = await fetch("/api/auth/me");
  const me = asked.ok ? await asked.json() : null;
  if (!me?.id || me.id !== user) throw new Error("Nobody is signed in.");
  await forget();
  const cache = await caches.open(YOURS);
  on = true;
  await own(cache, me.id);
  const drawn = (Array.isArray(parts) ? parts : []).filter(
    (p) => typeof p === "string" && PARTS.test(p),
  );
  for (const [key, path] of [[SHELL, PAGES[0]], ...[...DATA, ...drawn].map((p) => [p, p])]) {
    const response = await fetch(path);
    if (!response.ok) {
      await forget();
      throw new Error(`${path} couldn't be fetched.`);
    }
    await keep(cache, key, response);
  }
}

self.addEventListener("install", (event) => {
  // "reload": the page as the server has it now, not as the browser kept it.
  event.waitUntil(
    caches.open(KEPT).then((cache) => cache.add(new Request(OFFLINE, { cache: "reload" }))),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // Not what is someone's: a new worker is no reason to lose it.
      for (const name of await caches.keys())
        if (name !== KEPT && name !== YOURS) await caches.delete(name);
      // The browser starts fetching a page while this is still starting,
      // so a page isn't slower to load for its being here.
      if (self.registration.navigationPreload) await self.registration.navigationPreload.enable();
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // Signing out, or deleting the account: the copy goes before the request
  // leaves, whether or not it comes back.
  if (request.method === "POST" && LEAVING.includes(url.pathname)) {
    event.waitUntil(forget());
    return;
  }
  if (request.method !== "GET") return;
  if (request.mode === "navigate") {
    event.respondWith(page(event, url.pathname));
    return;
  }
  // A device whose switch is off: none of the rest is this worker's business.
  if (!on) return;
  if ((DATA.includes(url.pathname) && !url.search) || PARTS.test(url.pathname))
    event.respondWith(part(event, url.pathname));
});

// The switch on Account's page: "keep" answers whether a copy is kept now,
// "forget" that none is.
self.addEventListener("message", (event) => {
  const answer = (kept, why) => event.ports[0]?.postMessage({ kept, why });
  if (event.data?.type === "keep")
    event.waitUntil(
      start(event.data).then(
        () => answer(true),
        (failed) => answer(false, String(failed?.message ?? failed)),
      ),
    );
  if (event.data?.type === "forget") event.waitUntil(forget().then(() => answer(false)));
});
