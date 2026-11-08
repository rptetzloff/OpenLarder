// What /api/sources returns, and adding a book by ISBN.

export interface BookSummary {
  id: string;
  kind: "book" | "website" | "magazine" | "newspaper";
  // A website's, as "smittenkitchen.com".
  host: string | null;
  title: string;
  subtitle: string | null;
  authors: string[];
  cover_url: string | null;
  editions: number;
}

export interface Edition {
  id: string;
  title: string | null;
  isbn13: string | null;
  publisher: string | null;
  published_year: number | null;
  cover_url: string | null;
  open_library_url: string | null;
}

export interface Book {
  id: string;
  kind: "book" | "website" | "magazine" | "newspaper";
  host: string | null;
  // A website behind a subscription: linked, never copied.
  paywalled: boolean;
  title: string;
  subtitle: string | null;
  open_library_url: string | null;
  credits: { author_id: string; credited_as: string; role: string }[];
  editions: Edition[];
  // pages: one per edition it is in, newest first; null = not recorded.
  // issue: a magazine's or newspaper's recipe's issue; pages then its page.
  recipes: { id: string; title: string; pages: (string | null)[]; issue: string | null }[];
  // A magazine's or newspaper's issues, newest first.
  issues: { id: string; label: string; published_on: string | null }[];
  // The ingredients its recipes use most, with how many recipes use each.
  ingredients: { id: string; name: string; recipes: number }[];
}

// Resolves to the book's ID, whether it was added now or was already here
// (`existing`), or rejects with a reason to show beside the field.
export async function addByIsbn(isbn: string): Promise<{ id: string; existing: boolean }> {
  const res = await fetch("/api/sources", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ isbn }),
  });
  const body = await res.json().catch(() => ({}));
  if (res.status === 201) return { id: body.id, existing: false };
  if (res.status === 409 && body.detail?.source_id) return { id: body.detail.source_id, existing: true };
  const detail = typeof body.detail === "string" ? body.detail : "That didn't work. Try again.";
  throw new Error(detail);
}

// What linking a book to Open Library would do; see routers/sources.py.
export interface LinkPreview {
  open_library_url: string | null;
  title: string;
  subtitle: string | null;
  edition: {
    title: string | null;
    isbn13: string | null;
    publisher: string | null;
    published_year: number | null;
    cover_url: string | null;
    open_library_url: string;
    step: "fill" | "add";
    fills_isbn13: string | null;
  } | null;
  authors: {
    name: string;
    open_library_url: string;
    outcome: "linked" | "link" | "add" | "unmatched";
    credited_as: string | null;
  }[];
  problem: string | null;
}

async function post(path: string, reference: string) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reference }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}

export async function previewLink(bookId: string, reference: string): Promise<LinkPreview> {
  return post(`/api/sources/${bookId}/open-library/preview`, reference);
}

export async function linkToOpenLibrary(bookId: string, reference: string): Promise<void> {
  await post(`/api/sources/${bookId}/open-library`, reference);
}

// What the edit form sends: credits in order, each naming an author already
// credited or (author_id null) a new name; editions left out are unchanged.
export interface BookIn {
  title: string;
  subtitle: string;
  credits: { author_id: string | null; name: string; role: string }[];
  editions: { id: string; title: string; publisher: string; published_year: number | null }[];
  // A website's only.
  paywalled?: boolean;
}

export async function saveBook(bookId: string, body: BookIn): Promise<void> {
  const res = await fetch(`/api/sources/${bookId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const out = await res.json().catch(() => ({}));
    throw new Error(typeof out.detail === "string" ? out.detail : "That didn't save. Try again.");
  }
}

// A few books with every word of q in the title, subtitle or a credited
// name, for type-to-find pickers.
export async function findBooks(q: string, limit = 8): Promise<BookSummary[]> {
  return (await listSources(q, 0, limit)).sources;
}

// A page of sources, narrowed by q; total is how many match in all.
export async function listSources(
  q: string,
  offset = 0,
  limit?: number,
): Promise<{ sources: BookSummary[]; total: number }> {
  const query = new URLSearchParams({ q });
  if (offset) query.set("offset", String(offset));
  if (limit) query.set("limit", String(limit));
  const res = await fetch(`/api/sources?${query}`);
  if (!res.ok) throw new Error("The sources couldn't be loaded.");
  return res.json();
}

// One way the book here differs from Open Library now; for a cover, ours
// and theirs are image addresses.
export interface Difference {
  key: string;
  label: string;
  ours: string | null;
  theirs: string | null;
  cover: boolean;
}

export async function checkOpenLibrary(
  bookId: string,
): Promise<{ open_library_url: string; differences: Difference[] }> {
  const res = await fetch(`/api/sources/${bookId}/open-library/check`, { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}

// Takes the ticked differences; resolves to how many, and what still differs.
export async function takeFromOpenLibrary(
  bookId: string,
  keys: string[],
): Promise<{ taken: number; differences: Difference[] }> {
  const res = await fetch(`/api/sources/${bookId}/open-library/take`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keys }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}

// A website as a source: the one already here for that site, or a new one.
export async function addWebsite(
  address: string,
  name: string,
  paywalled: boolean,
  authors: string[] = [],
): Promise<{ id: string; existing: boolean }> {
  const res = await fetch("/api/sources/websites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address, name: name || null, paywalled, authors }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}

// A magazine or newspaper as a source: the one already here, or a new one.
export async function addPeriodical(
  kind: "magazine" | "newspaper",
  title: string,
  authors: string[] = [],
): Promise<{ id: string; existing: boolean }> {
  const res = await fetch("/api/sources/periodicals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, title, authors }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}

// What a kind of source is called in a sentence: "this magazine".
export const KIND_NAMES: Record<string, string> = {
  book: "book",
  website: "website",
  magazine: "magazine",
  newspaper: "newspaper",
};

// An issue as people say it: one named by its date ("2024-09-18", as a
// newspaper's is) in words, "September 18, 2024"; any other as named.
export function issueName(label: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(label)) return label;
  const [y, m, d] = label.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { dateStyle: "long" });
}
