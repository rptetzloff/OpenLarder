import type { Review } from "./review";
// What /api/sources returns, and adding a book by ISBN.

import type { BuyLink } from "./buying";
import type { Tag } from "./tags";

export interface BookSummary {
  id: string;
  kind: "book" | "website" | "magazine" | "newspaper" | "tv_show" | "podcast" | "video_channel" | "social" | "packaging" | "family";
  // A website's, as "smittenkitchen.com".
  host: string | null;
  title: string;
  subtitle: string | null;
  authors: string[];
  cover_url: string | null;
  editions: number;
  recipes: number;
  // A family collection only its owner sees.
  private: boolean;
}

export interface Edition {
  id: string;
  title: string | null;
  isbn13: string | null;
  publisher: string | null;
  published_year: number | null;
  cover_url: string | null;
  open_library_url: string | null;
  // Where to buy it; none until an affiliate ID is set.
  buy: BuyLink[];
}

export interface Book {
  id: string;
  kind: "book" | "website" | "magazine" | "newspaper" | "tv_show" | "podcast" | "video_channel" | "social" | "packaging" | "family";
  host: string | null;
  // A website behind a subscription: linked, never copied.
  paywalled: boolean;
  title: string;
  subtitle: string | null;
  open_library_url: string | null;
  // credited_as is what's stored (the edit form's); name is what to show.
  credits: { author_id: string; credited_as: string; name: string; role: string }[];
  editions: Edition[];
  // pages: one per edition it is in, newest first; null = not recorded.
  // issue: a magazine's or newspaper's recipe's issue; pages then its page.
  // episode and at: a show's recipe's episode, and the time in it.
  // Its tags, which every recipe in it has too.
  tags: Tag[];
  recipes: {
    id: string;
    title: string;
    // The chapter or section it's in, as the book names it.
    chapter: string | null;
    pages: (string | null)[];
    issue: string | null;
    episode: string | null;
    at: string | null;
    // A book's recipe: its page in each edition it's in (null, not recorded).
    editions: { edition_id: string; page: string | null }[];
    // The first of its ingredient lines, and how many there are.
    lines: string[];
    line_count: number;
    // Another recipe here uses it as a component.
    component: boolean;
    // published, or (for its maker and moderators) waiting or sent back.
    review: Review;
  }[];
  // A magazine's or newspaper's issues, newest first.
  issues: { id: string; label: string; published_on: string | null }[];
  // A family collection only its owner sees; and whether you may add to and
  // change it.
  private: boolean;
  editable: boolean;
  // published, or (for its maker and moderators) pending or returned, with
  // the moderator's note; and whether you may change its details and tags.
  review: Review;
  review_note: string | null;
  details_editable: boolean;
  tags_editable: boolean;
  // A family collection's: whose it is, whether you may rename, delete or
  // share it, and the groups it's shared with (every one for its owner; the
  // ones you're in otherwise).
  owner_name: string | null;
  manageable: boolean;
  shared_with: { id: string; name: string }[];
  // A TV show's, podcast's or video channel's episodes, in order.
  episodes: {
    id: string;
    name: string;
    season: number | null;
    number: number | null;
    title: string | null;
    url: string | null;
    aired_on: string | null;
  }[];
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
  throw new Error(reason(body));
}

// The server's reason: a sentence, or {message} (someone else's book that's
// waiting for review is named but not linked).
function reason(body: { detail?: unknown }): string {
  const detail = body.detail as string | { message?: string } | undefined;
  if (typeof detail === "string") return detail;
  return detail?.message ?? "That didn't work. Try again.";
}

// A book Open Library doesn't know, from its title and authors. A
// contributor's waits for review.
export async function addManually(
  title: string,
  authors: string[],
  year: number | null,
  isbn: string,
): Promise<{ id: string; existing: boolean }> {
  const res = await fetch("/api/sources/manual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, authors, year, isbn: isbn.trim() || null }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(reason(body));
  return body;
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

// Suggest a change to a published source's details, for a moderator to
// apply (routers/proposals.py).
export async function proposeBookChange(
  bookId: string,
  body: BookIn & { reason: string | null },
): Promise<void> {
  const res = await fetch(`/api/sources/${bookId}/proposals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const out = await res.json().catch(() => ({}));
    throw new Error(typeof out.detail === "string" ? out.detail : "That didn't send. Try again.");
  }
}

// Merging one book into another (book_merge.py): what would move, and doing it.
export interface MergePlan {
  editions: number;
  recipes: number;
  credits: number;
  same_titles: string[];
}

export async function mergePlan(bookId: string, into: string): Promise<MergePlan> {
  const res = await fetch(`/api/sources/${bookId}/merge?into=${into}`);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}

export async function mergeBook(bookId: string, into: string): Promise<string> {
  const res = await fetch(`/api/sources/${bookId}/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ into }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't merge.");
  return body.id;
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
  // "recent": newest added first, for the front page; "recipes": the most
  // recipes first; by title otherwise.
  sort?: "recent" | "recipes",
  // Only these kinds; every kind when empty.
  kinds: string[] = [],
  // Only sources with at least this many recipes; all of them when 0.
  minRecipes = 0,
): Promise<{ sources: BookSummary[]; total: number; kinds: Record<string, number> }> {
  const query = new URLSearchParams({ q });
  if (minRecipes) query.set("min_recipes", String(minRecipes));
  if (offset) query.set("offset", String(offset));
  if (limit) query.set("limit", String(limit));
  if (sort) query.set("sort", sort);
  for (const kind of kinds) query.append("kind", kind);
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

// A TV show, podcast or video channel as a source: the one already here,
// or a new one.
export async function addShow(
  kind: "tv_show" | "podcast" | "video_channel",
  title: string,
  authors: string[] = [],
): Promise<{ id: string; existing: boolean }> {
  const res = await fetch("/api/sources/shows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, title, authors }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}

// A social media account, or a product whose packaging prints recipes.
export async function addNamed(
  kind: "social" | "packaging",
  title: string,
  authors: string[] = [],
): Promise<{ id: string; existing: boolean }> {
  const res = await fetch(`/api/sources/${kind}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, authors }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}

// A family collection of yours. private: only you see it (only an admin can
// add a public one for now); acknowledged: the form's tick box.
export async function addFamily(
  title: string,
  isPrivate: boolean,
  acknowledged: boolean,
): Promise<{ id: string; existing: boolean }> {
  const res = await fetch("/api/sources/family", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, private: isPrivate, acknowledged }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}

// Rename a family collection.
export async function renameFamily(id: string, title: string): Promise<void> {
  const res = await fetch(`/api/sources/${id}/family`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  }
}

// Delete a family collection and its recipes.
export async function removeFamily(id: string): Promise<void> {
  const res = await fetch(`/api/sources/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  }
}

export const SHOWS = ["tv_show", "podcast", "video_channel"];

// What a kind of source is called in a sentence: "this magazine".
export const KIND_NAMES: Record<string, string> = {
  book: "book",
  website: "website",
  magazine: "magazine",
  newspaper: "newspaper",
  tv_show: "TV show",
  podcast: "podcast",
  video_channel: "video channel",
  social: "social media account",
  packaging: "product",
  family: "family collection",
};

// A kind of source in the plural, as a heading says it: "Books", "TV shows".
export function kindPlural(kind: string): string {
  const name = KIND_NAMES[kind] ?? "source";
  return `${name[0].toUpperCase()}${name.slice(1)}s`;
}

// An issue as people say it: one named by its date ("2024-09-18", as a
// newspaper's is) in words, "September 18, 2024"; any other as named.
export function issueName(label: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(label)) return label;
  const [y, m, d] = label.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { dateStyle: "long" });
}
