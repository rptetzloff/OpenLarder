// Authors: what /api/authors returns, and fixing one.

import type { BookSummary } from "./books";

export interface AuthorSummary {
  id: string;
  name: string;
  books: number;
}

export interface Author {
  id: string;
  name: string;
  kind: "person" | "organisation";
  open_library_url: string | null;
  links: { id: string; url: string; label: string | null }[];
  // This author's roles on each book, and the name it prints for them.
  books: (BookSummary & { roles: string[]; credited_as: string })[];
  // People credited on the same books, most shared first.
  coauthors: AuthorSummary[];
}

async function send(path: string, method: string, body?: unknown) {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const out = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof out.detail === "string" ? out.detail : "That didn't work. Try again.");
  }
  return out;
}

export async function listAuthors(
  q: string,
  offset = 0,
): Promise<{ authors: AuthorSummary[]; total: number }> {
  const query = new URLSearchParams({ q });
  if (offset) query.set("offset", String(offset));
  return send(`/api/authors?${query}`, "GET");
}

export async function fetchAuthor(id: string): Promise<Author | null> {
  const res = await fetch(`/api/authors/${id}`);
  if (res.status === 404 || res.status === 422) return null;
  if (!res.ok) throw new Error("This author couldn't be loaded.");
  return res.json();
}

export async function saveAuthor(id: string, name: string, kind: Author["kind"]) {
  return send(`/api/authors/${id}`, "PATCH", { name, kind });
}

export async function addLink(
  id: string,
  url: string,
  label: string,
): Promise<Author["links"][number]> {
  return send(`/api/authors/${id}/links`, "POST", { url, label: label || null });
}

export async function removeLink(id: string, linkId: string): Promise<void> {
  await send(`/api/authors/${id}/links/${linkId}`, "DELETE");
}
