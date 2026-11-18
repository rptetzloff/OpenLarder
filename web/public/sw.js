// OpenLarder's service worker. It has one job: a page of the site's own to
// show when there's no connection, where the browser would show its error.
// *Ray, 2026-11-17: the installable web app.* Opened from its icon with no
// signal, an app that shows the browser's error page looks broken.
//
// It keeps one page (/offline.html) and nothing else. Every request goes to
// the network exactly as if this weren't here; only a page that can't be
// fetched at all is answered with the one kept. Nothing of the catalog and
// nothing of anyone's is on the device, so there is nothing to go stale and
// nothing to take off at sign-out.
//
// Changing it: a browser fetches this file again on its own (main.py sends
// it no-cache, so Cloudflare keeps no old one) and the new one takes over
// at once. To be rid of it, ship one whose "activate" calls
// self.registration.unregister(); deleting the file leaves the old one
// running in every browser that has it.

// A new name when the page kept must be fetched again; the old is deleted.
const KEPT = "openlarder-offline-v1";
const OFFLINE = "/offline.html";

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
      for (const name of await caches.keys()) if (name !== KEPT) await caches.delete(name);
      // The browser starts fetching a page while this is still starting,
      // so a page isn't slower to load for its being here.
      if (self.registration.navigationPreload) await self.registration.navigationPreload.enable();
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  // Only a page being opened. Scripts, pictures, the API and a form being
  // sent are none of this worker's business.
  if (event.request.mode !== "navigate" || event.request.method !== "GET") return;
  event.respondWith(
    (async () => {
      try {
        return (await event.preloadResponse) || (await fetch(event.request));
      } catch {
        // No answer at all: no connection, or no server. An answer that is
        // an error is the server's to give, and was returned above.
        return (await caches.match(OFFLINE)) || Response.error();
      }
    })(),
  );
});
