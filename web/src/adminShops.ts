// Shops, for administrators: what /api/admin/shops takes and returns
// (routers/shops.py).

export type ShopKind = "bookseller" | "grocer";
export type Builder = "bookshop" | "amazon" | "wrapped" | "template";

export interface Shop {
  id: string;
  key: string;
  kind: ShopKind;
  label: string;
  builder: Builder;
  affiliate_id: string | null;
  wrapper_template: string | null;
  product_template: string | null;
  format: "print" | "ebook" | null;
  earns: "affiliate" | "referral" | "none";
  note: string | null;
  enabled: boolean;
  // On the site now: switched on, with what its builder needs.
  shown: boolean;
  // Switched on and not shown: what it still needs.
  needs: string | null;
  // Its setting is still in this environment variable, not on the shop.
  variable: string | null;
  clicks_30_days: number;
  clicks: number;
  updated_at: string;
  updated_by: string | null;
}

export interface ShopGroup {
  kind: ShopKind;
  label: string;
  shops: Shop[];
}

// What a form sends: a shop's fields, and for a new one its key and kind.
export interface ShopFields {
  label: string;
  builder: Builder;
  affiliate_id: string | null;
  wrapper_template: string | null;
  product_template: string | null;
  format: "print" | "ebook" | null;
  earns: "affiliate" | "referral" | "none";
  note: string | null;
  enabled: boolean;
}

export interface Tried {
  url: string;
  host: string;
  sample: string;
}

// What each kind's own address may ask for, as routers/shops.py checks.
export const PLACEHOLDERS: Record<ShopKind, string[]> = {
  bookseller: ["{isbn13}", "{isbn10}", "{title}", "{author}", "{words}", "{id}"],
  grocer: ["{term}", "{id}"],
};
export const BUILDERS: Record<ShopKind, [Builder, string][]> = {
  bookseller: [
    ["wrapped", "Its own address, inside an affiliate network's deep link"],
    ["template", "Its own address, as written"],
    ["bookshop", "Bookshop.org's, with the affiliate id in it"],
    ["amazon", "Amazon's, made for each book, with the Associates tag"],
  ],
  grocer: [
    ["wrapped", "Its own address, inside an affiliate network's deep link"],
    ["template", "Its own address, as written"],
    ["amazon", "Amazon Fresh's, made for each ingredient, with the Associates tag"],
  ],
};

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const out = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof out.detail === "string" ? out.detail : "That didn't work. Try again.");
  }
  return out;
}

export const listShops = () => send<ShopGroup[]>("/api/admin/shops", "GET");
export const addShop = (kind: ShopKind, key: string, fields: ShopFields) =>
  send<ShopGroup[]>("/api/admin/shops", "POST", { ...fields, kind, key });
export const changeShop = (id: string, fields: ShopFields) =>
  send<ShopGroup[]>(`/api/admin/shops/${id}`, "PUT", fields);
export const switchShop = (id: string, enabled: boolean) =>
  send<ShopGroup[]>(`/api/admin/shops/${id}/enabled`, "PUT", { enabled });
export const moveShop = (id: string, to: "up" | "down") =>
  send<ShopGroup[]>(`/api/admin/shops/${id}/move`, "POST", { to });
export const removeShop = (id: string) => send<ShopGroup[]>(`/api/admin/shops/${id}`, "DELETE");
export const tryShop = (kind: ShopKind, key: string, fields: ShopFields) =>
  send<Tried>("/api/admin/shops/test", "POST", { ...fields, kind, key });
