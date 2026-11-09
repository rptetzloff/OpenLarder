// Authors: what /api/authors returns, and fixing one.

import type { BookSummary } from "./books";

export interface AuthorSummary {
  id: string;
  name: string;
  sources: number;
}

// As the Authors page lists them: also how many recipes their sources hold,
// and the source with the most.
export interface AuthorListed extends AuthorSummary {
  kind: "person" | "organisation";
  recipes: number;
  known_for: { id: string; title: string } | null;
}

export interface Author {
  id: string;
  name: string;
  kind: "person" | "organisation";
  open_library_url: string | null;
  // From Wikidata, when the author is on it. For an organisation, born is
  // when it was founded.
  wikidata_url: string | null;
  born_year: number | null;
  died_year: number | null;
  country: string | null;
  website: string | null;
  links: { id: string; url: string; label: string | null }[];
  // This author's roles on each book, and the name it prints for them.
  sources: (BookSummary & { roles: string[]; credited_as: string })[];
  // People credited on the same books, most shared first.
  coauthors: AuthorSummary[];
  // Others whose names compare the same: likely one person, to merge.
  same_name: AuthorSummary[];
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

// sort "recipes": the most recipes first, rather than A to Z; kind: only
// people, or only organisations.
export async function listAuthors(
  q: string,
  offset = 0,
  options: { sort?: "name" | "recipes"; kind?: "person" | "organisation" | null } = {},
): Promise<{ authors: AuthorListed[]; total: number }> {
  const query = new URLSearchParams({ q });
  if (offset) query.set("offset", String(offset));
  if (options.sort === "recipes") query.set("sort", "recipes");
  if (options.kind) query.set("kind", options.kind);
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

// Merges this author into another; resolves to the one that's left.
export async function mergeAuthor(id: string, into: string): Promise<AuthorSummary> {
  return send(`/api/authors/${id}/merge`, "POST", { into });
}

// Says which Wikidata item the author is (an ID or a link), fetching its
// facts; null takes it off. Resolves to the author as it now stands.
export async function setWikidata(id: string, reference: string | null): Promise<Author> {
  return send(`/api/authors/${id}/wikidata`, "PUT", { reference });
}

export interface WikidataRun {
  checked: number;
  found: number;
  // Authors whose item another author has: probably one person twice.
  clashes: { author: AuthorSummary; other: AuthorSummary }[];
  remaining: number;
}

// Asks Wikidata about the next batch of authors not asked lately.
export async function checkWikidata(): Promise<WikidataRun> {
  return send("/api/authors/wikidata", "POST");
}

// "1912–2004", "Born 1950", "Founded 1993": the years an author's facts give.
export function lifespan(a: Pick<Author, "kind" | "born_year" | "died_year">): string {
  if (a.kind === "organisation") return a.born_year ? `Founded ${a.born_year}` : "";
  if (a.born_year && a.died_year) return `${a.born_year}–${a.died_year}`;
  if (a.born_year) return `Born ${a.born_year}`;
  return a.died_year ? `Died ${a.died_year}` : "";
}
