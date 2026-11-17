// Equipment's shop links (kitchen.py): where a piece of equipment's Shop
// link goes, as grocery.ts is for an ingredient's. Ray's equipment spec,
// 2026-11-15, Part 8.
//
// The first shop on offer, and each person may choose another, as they
// choose a grocer (Ray, 2026-11-16: equipment is treated as ingredients
// are). Signed in, the choice is kept with the account
// (/api/account/kitchen-shop); signed out, this browser keeps it.

import { ref } from "vue";
import type { Me } from "./me";

export interface KitchenShop {
  key: string;
  label: string;
  note: string | null;
}

const KEY = "openlarder.kitchen-shop";

function readLocal(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

// The shops on offer: those switched on with their affiliate setting in place.
export const kitchenShops = ref<KitchenShop[] | null>(null);
let asked: Promise<void> | null = null;
export function loadKitchenShops(): Promise<void> {
  asked ??= fetch("/api/kitchen-shops")
    .then((r) => (r.ok ? r.json() : []))
    .then((found: KitchenShop[]) => {
      kitchenShops.value = found;
    })
    .catch(() => {
      kitchenShops.value = [];
    });
  return asked;
}

// The choice: this browser's, until a signed-in account's arrives.
export const chosen = ref<string | null>(readLocal());

export function adoptKitchenShop(user: Me | null | undefined) {
  if (user?.kitchen_shop) chosen.value = user.kitchen_shop;
}

// The shop links go to: the one chosen, if it's on offer; else the first.
export function kitchenShopNow(offered = kitchenShops.value): KitchenShop | null {
  if (!offered?.length) return null;
  return offered.find((k) => k.key === chosen.value) ?? offered[0];
}

export function equipmentHref(shop: KitchenShop, equipmentId: string): string {
  return `/go/equipment/${shop.key}/${equipmentId}?from=${encodeURIComponent(location.pathname)}`;
}

export async function chooseKitchenShop(key: string, signedIn: boolean): Promise<void> {
  chosen.value = key;
  try {
    localStorage.setItem(KEY, key);
  } catch {
    // A browser that keeps nothing still has the choice for this visit.
  }
  if (!signedIn) return;
  const res = await fetch("/api/account/kitchen-shop", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kitchen_shop: key }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "That didn't save. Try again.");
  }
}
