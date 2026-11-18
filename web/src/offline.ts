// What the site does with no connection (public/sw.js): a page of its own
// to say so, and, on a device where someone has switched it on, a copy of
// what is theirs to read. *Ray, 2026-11-17: "only where switched on".*
// The service worker does the keeping; this is the switch, and what the
// page is told when the worker answers from the copy.
import { ref } from "vue";

// The copy, where there is one: the worker's name for it.
const YOURS = "openlarder-yours-v1";

// When the page is showing the copy: how old the oldest thing it was
// answered with is. Nothing while everything has come from the server.
export const keptAsOf = ref<number | null>(null);

// The service worker is asked for once the page has loaded, so it competes
// with nothing the page needs. Only in a built site: under the dev server
// there is no build to be offline from, and a worker left in the browser
// would get in its way.
export function keepAnOfflinePage() {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  // Said by the worker each time it answers from the copy.
  navigator.serviceWorker.addEventListener("message", (event) => {
    if (event.data?.type !== "kept" || typeof event.data.at !== "number") return;
    keptAsOf.value = Math.min(keptAsOf.value ?? event.data.at, event.data.at);
  });
  window.addEventListener("load", () => {
    // Refused (a private window, a browser set against it): the site works
    // as it did, with the browser's own error page when there's no signal.
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}

// Whether this browser can keep a copy at all.
export const canKeep = () => "serviceWorker" in navigator && "caches" in window;

// Whether this device keeps one now.
export async function keptHere(): Promise<boolean> {
  return canKeep() && (await caches.has(YOURS));
}

// Asks the worker, and waits for its answer: whether a copy is kept now,
// and why not if it was meant to be.
async function ask(message: object): Promise<{ kept: boolean; why?: string }> {
  const worker = (await navigator.serviceWorker.ready).active;
  if (!worker) throw new Error("This browser hasn't started the part of OpenLarder that keeps a copy.");
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    // Long enough for a long saved list: each recipe is fetched as it's kept.
    const late = setTimeout(() => reject(new Error("That took too long. Try again.")), 180_000);
    channel.port1.onmessage = (event) => {
      clearTimeout(late);
      resolve(event.data);
    };
    worker.postMessage(message, [channel.port2]);
  });
}

// Keeps a copy on this device for whoever is signed in: the four pages,
// what they ask for, and what this page was drawn with, which the worker
// fetches and keeps. All of it or none.
export async function keepHere(user: string): Promise<void> {
  const parts = performance
    .getEntriesByType("resource")
    .map((entry) => new URL(entry.name, location.href))
    .filter((url) => url.origin === location.origin)
    .map((url) => url.pathname);
  const answer = await ask({ type: "keep", user, parts: [...new Set(parts)] });
  if (!answer.kept) throw new Error("The copy couldn't be kept. Check your connection and try again.");
}

// A recipe has been saved, or taken off the list: where a copy is kept,
// the worker fetches the list again, and keeps or lets go of the recipe.
export function savedChanged() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.controller?.postMessage({ type: "saved" });
}

// Takes the copy off this device.
export async function forgetHere(): Promise<void> {
  await ask({ type: "forget" });
}
