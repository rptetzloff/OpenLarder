// A page of the site's own for when there's no connection (public/sw.js,
// public/offline.html): the service worker that keeps it is asked for
// here, once the page has loaded, so it competes with nothing the page
// needs. Only in a built site: under the dev server there is no build to
// be offline from, and a worker left in the browser would get in its way.
export function keepAnOfflinePage() {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    // Refused (a private window, a browser set against it): the site works
    // as it did, with the browser's own error page when there's no signal.
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}
