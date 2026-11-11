// Ingredients' grocery links (grocery.py): Instacart first, and each person
// may choose another, as Instacart may have nothing near them (Ray,
// 2026-11-11). Signed in, the choice is kept with the account
// (/api/account/grocer); signed out, this browser keeps it.

import { ref } from "vue";
import type { Me } from "./me";

export interface Grocer {
  key: string;
  label: string;
  note: string | null;
}

const KEY = "openlarder.grocer";

function readLocal(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

// The grocers on offer: those whose affiliate setting is in place.
export const grocers = ref<Grocer[] | null>(null);
let asked: Promise<void> | null = null;
export function loadGrocers(): Promise<void> {
  asked ??= fetch("/api/grocers")
    .then((r) => (r.ok ? r.json() : []))
    .then((g: Grocer[]) => {
      grocers.value = g;
    })
    .catch(() => {
      grocers.value = [];
    });
  return asked;
}

// The choice: this browser's, until a signed-in account's arrives.
export const chosen = ref<string | null>(readLocal());

export function adoptGrocer(user: Me | null | undefined) {
  if (user?.grocer) chosen.value = user.grocer;
}

// The grocer links go to: the one chosen, if it's on offer; else the first.
export function grocerNow(offered = grocers.value): Grocer | null {
  if (!offered?.length) return null;
  return offered.find((g) => g.key === chosen.value) ?? offered[0];
}

export function grocerHref(grocer: Grocer, ingredientId: string): string {
  return `/go/grocer/${grocer.key}/${ingredientId}?from=${encodeURIComponent(location.pathname)}`;
}

export async function chooseGrocer(key: string, signedIn: boolean): Promise<void> {
  chosen.value = key;
  try {
    localStorage.setItem(KEY, key);
  } catch {
    // A browser that keeps nothing still has the choice for this visit.
  }
  if (!signedIn) return;
  const res = await fetch("/api/account/grocer", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grocer: key }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "That didn't save. Try again.");
  }
}
