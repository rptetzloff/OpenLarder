// Your shelf (routers/shelf.py): the books you own, and which edition.

export interface OnShelf {
  source_id: string;
  on_shelf: boolean;
  edition_id: string | null;
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

async function failed(res: Response): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work. Try again.");
}

export async function myShelf(): Promise<ShelfBook[]> {
  const res = await fetch("/api/shelf");
  if (!res.ok) await failed(res);
  return (await res.json()).books;
}

export async function onShelf(sourceId: string): Promise<OnShelf> {
  const res = await fetch(`/api/shelf/${sourceId}`);
  if (!res.ok) await failed(res);
  return res.json();
}

export async function putOnShelf(sourceId: string, editionId: string | null): Promise<OnShelf> {
  const res = await fetch(`/api/shelf/${sourceId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edition_id: editionId }),
  });
  if (!res.ok) await failed(res);
  return res.json();
}

export async function takeOffShelf(sourceId: string): Promise<void> {
  const res = await fetch(`/api/shelf/${sourceId}`, { method: "DELETE" });
  if (!res.ok) await failed(res);
}
