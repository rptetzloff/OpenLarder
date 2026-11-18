// Installing OpenLarder as an app, where the browser offers to. *Ray,
// 2026-11-17, asked about apps and shown the three ways: the installable
// web app, for now.* It is the site, opened from its own icon without the
// browser's bars.
//
// Chrome, Edge and Samsung Internet, on Android and on a computer, tell a
// page when it can be installed (`beforeinstallprompt`) and let it ask
// when the person chooses to. Kept here until then, so the asking is the
// footer's "Install the app" and not a bar the browser puts over the page
// on a first visit (Claude's choice: nobody came to be asked that).
// Safari tells a page nothing: on an iPhone it is Share, then Add to Home
// Screen, and nothing here can offer it.
import { computed, ref } from "vue";

interface InstallOffer extends Event {
  prompt(): Promise<unknown>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const offer = ref<InstallOffer | null>(null);

// Whether there is an offer to take: none in a browser that makes none,
// none once it's installed, and none after it's been answered, since a
// browser's offer can be used once.
export const canInstall = computed(() => offer.value !== null);

// Called once, as the app starts: the browser may make its offer at any
// time after the page loads.
export function watchForInstall() {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    offer.value = event as InstallOffer;
  });
  window.addEventListener("appinstalled", () => {
    offer.value = null;
  });
}

// Shows the browser's own question; whatever the answer, the offer is
// spent. A browser may refuse to ask (it wants the press of a person, and
// an offer can be used once): nothing is said then, as nothing can be done.
export async function install() {
  const asked = offer.value;
  if (!asked) return;
  offer.value = null;
  try {
    await asked.prompt();
    await asked.userChoice;
  } catch {
    // Refused, or the offer was withdrawn.
  }
}
