// The edit history (routers/history.py): a record's changes, newest first,
// or the latest across the catalog for moderators.

export interface Field {
  field: string;
  before: unknown;
  after: unknown;
}

export interface Entry {
  table: string;
  what: string;
  action: "added" | "changed" | "removed";
  name: string | null;
  fields: Field[];
}

export interface Change {
  id: string;
  at: string;
  by: string | null;
  withheld: boolean;
  via: string | null;
  source_id: string | null;
  entries: Entry[];
}

export type Kind = "sources" | "recipes" | "ingredients" | "authors";

async function get(url: string): Promise<Change[]> {
  const res = await fetch(url);
  if (!res.ok) throw new Error("The history couldn't be loaded. Try again.");
  return res.json();
}

export const historyOf = (kind: Kind, id: string) => get(`/api/${kind}/${id}/history`);

// Undo a change (revert.py): resolves to how many rows it undid, or
// rejects with why it can't be (a later change to the same records).
export async function revertChange(id: string): Promise<number> {
  const res = await fetch(`/api/changes/${id}/revert`, { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body.undone;
}

export const recentChanges = (by: string) =>
  get(`/api/changes${by ? `?by=${encodeURIComponent(by)}` : ""}`);

// How a change came about, for people: who, or why no one is named.
export function madeBy(c: Change): string {
  if (c.withheld) return "Someone";
  if (c.by) return c.by;
  return "OpenLarder";
}

export function cameThrough(via: string | null): string | null {
  if (!via) return null;
  if (via.startsWith("import")) return "a bulk import";
  if (via.startsWith("suggestion")) return "an accepted suggestion";
  if (via.startsWith("revert")) return "an undo";
  return via;
}

// A stored value, as it reads.
export function shown(value: unknown): string {
  if (value === null || value === undefined || value === "") return "nothing";
  if (value === true) return "yes";
  if (value === false) return "no";
  if (typeof value === "string") return `“${value}”`;
  return String(value);
}

// What a column reads as: an id names what it points at.
const LABELS: Record<string, string> = {
  ingredient_id: "ingredient",
  parent_id: "parent",
  from_ingredient_id: "swap from",
  to_ingredient_id: "swap to",
  author_id: "author",
  tag_id: "tag",
  diet_tag_id: "diet",
  edition_id: "edition",
  sub_recipe_id: "sub-recipe",
  issue_id: "issue",
  episode_id: "episode",
  web_page_id: "web page",
  isbn13: "ISBN",
};
export const label = (field: string) => LABELS[field] ?? field.replace(/_/g, " ");
