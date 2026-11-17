// Equipment's shop links (kitchen.py): where a piece of equipment's Shop
// link goes, as grocery.ts is for an ingredient's. Ray's equipment spec,
// 2026-11-15, Part 8.
//
// The shop is the first on offer. A grocer is each person's to choose,
// since one may have nothing near them; nothing here chooses yet.

import { ref } from "vue";

export interface KitchenShop {
  key: string;
  label: string;
  note: string | null;
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

// The shop links go to: the first on offer, or none.
export function kitchenShopNow(offered = kitchenShops.value): KitchenShop | null {
  return offered?.length ? offered[0] : null;
}

export function equipmentHref(shop: KitchenShop, equipmentId: string): string {
  return `/go/equipment/${shop.key}/${equipmentId}?from=${encodeURIComponent(location.pathname)}`;
}
