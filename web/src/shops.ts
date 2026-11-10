// Each person's buy-link shops: the order they want them in, and those they
// hide; one always shows (Ray, 2026-11-09). Signed in, the choice is kept
// with the account (/api/account/shops); signed out, this browser keeps it.

import { ref } from "vue";
import type { BuyLink } from "./buying";
import type { Me } from "./me";

export interface ShopPrefs {
  order: string[];
  hidden: string[];
}

const KEY = "openlarder.shops";

function readLocal(): ShopPrefs | null {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "null");
    return saved && Array.isArray(saved.order) && Array.isArray(saved.hidden) ? saved : null;
  } catch {
    return null;
  }
}

// The choice in force: this browser's, until a signed-in account's arrives.
export const shopPrefs = ref<ShopPrefs | null>(readLocal());

export function adoptAccount(user: Me | null | undefined) {
  if (user?.shops) shopPrefs.value = user.shops;
}

// The links in the order chosen, without those hidden; all of them, rather
// than none, if every one offered here was hidden.
export function arrange(links: BuyLink[], prefs = shopPrefs.value): BuyLink[] {
  if (!prefs) return links;
  const rank = (key: string) => {
    const i = prefs.order.indexOf(key);
    return i === -1 ? prefs.order.length + links.findIndex((l) => l.retailer === key) : i;
  };
  const ordered = [...links].sort((a, b) => rank(a.retailer) - rank(b.retailer));
  const shown = ordered.filter((l) => !prefs.hidden.includes(l.retailer));
  return shown.length ? shown : ordered;
}

// Keeps the choice in this browser, and with the account when signed in;
// rejects with the server's reason.
export async function saveShopPrefs(prefs: ShopPrefs, signedIn: boolean): Promise<void> {
  shopPrefs.value = prefs;
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    // A browser that keeps nothing still has the choice for this visit.
  }
  if (!signedIn) return;
  const res = await fetch("/api/account/shops", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prefs),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "That didn't save. Try again.");
  }
}
