// Your shelf (routers/shelf.py): the books you own, and which edition;
// shared with household groups as a larder list is.

export interface GroupRef {
  id: string;
  name: string;
}

// A shelf shared with you, and whether a book is on it.
export interface OtherShelf {
  owner_id: string;
  owner_name: string | null;
  editable: boolean;
  on_shelf: boolean;
  edition_id: string | null;
}

export interface OnShelf {
  source_id: string;
  on_shelf: boolean;
  edition_id: string | null;
  others: OtherShelf[];
}

export interface ShelfBook {
  id: string;
  kind: string;
  host: string | null;
  title: string;
  subtitle: string | null;
  authors: string[];
  cover_url: string | null;
  editions: number;
  recipes: number;
  private: boolean;
  edition_id: string | null;
  edition_year: number | null;
  edition_isbn13: string | null;
  added_at: string;
}

export interface SharedShelf {
  owner_id: string;
  owner_name: string | null;
  // Whether you may change what's on it.
  editable: boolean;
  // The groups of yours it's shared through.
  through: GroupRef[];
  books: ShelfBook[];
}

export interface Shelf {
  books: ShelfBook[];
  // The groups yours is shared with, and your groups to choose from.
  shared_with: GroupRef[];
  groups: GroupRef[];
  shared: SharedShelf[];
}

async function failed(res: Response): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work. Try again.");
}

// Someone else's shelf, shared with you to change, or your own.
const whose = (owner?: string) => (owner ? `?owner=${owner}` : "");

export async function myShelf(): Promise<Shelf> {
  const res = await fetch("/api/shelf");
  if (!res.ok) await failed(res);
  return res.json();
}

export async function onShelf(sourceId: string): Promise<OnShelf> {
  const res = await fetch(`/api/shelf/${sourceId}`);
  if (!res.ok) await failed(res);
  return res.json();
}

export async function putOnShelf(
  sourceId: string,
  editionId: string | null,
  owner?: string,
): Promise<OnShelf> {
  const res = await fetch(`/api/shelf/${sourceId}${whose(owner)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edition_id: editionId }),
  });
  if (!res.ok) await failed(res);
  return res.json();
}

export async function takeOffShelf(sourceId: string, owner?: string): Promise<void> {
  const res = await fetch(`/api/shelf/${sourceId}${whose(owner)}`, { method: "DELETE" });
  if (!res.ok) await failed(res);
}

export async function shareShelf(groups: string[]): Promise<Shelf> {
  const res = await fetch("/api/shelf/groups", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ groups }),
  });
  if (!res.ok) await failed(res);
  return res.json();
}
