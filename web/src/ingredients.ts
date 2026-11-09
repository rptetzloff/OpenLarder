// Canonical ingredients: what /api/ingredients returns.

import { issueName } from "./books";
import type { Swap } from "./substitutions";

export interface IngredientSummary {
  id: string;
  name: string;
  recipes: number;
  // What it comes under, and its other names ("Root Ginger (UK)").
  parent?: { id: string; name: string } | null;
  aliases?: string[];
}

export interface IngredientList {
  ingredients: IngredientSummary[];
  total: number;
}

export interface Ingredient {
  id: string;
  name: string;
  // Other names lines are matched by: names it had, and ingredients merged in.
  aliases: { id: string; name: string }[];
  // Broader and narrower: cheese above cheddar, aged cheddar below it.
  parent: { id: string; name: string } | null;
  children: { id: string; name: string }[];
  // With the line naming it, as written.
  recipes: (Listed & { line: string | null })[];
  // Recipes using exactly this one; and how many the list holds in all.
  total: number;
  listed_total: number;
  // Recipes using it or anything under it, as search counts them.
  family_total: number;
  // What can stand in for it.
  swaps: Swap[];
}

// A recipe in a listing, and where it is: its source's kind, cover and
// credits, and a magazine's issue, a show's episode and time, or a site.
export interface Listed {
  id: string;
  title: string;
  source_id: string;
  source_title: string;
  pages: string[];
  source_kind: string;
  cover_url: string | null;
  authors: string[];
  issue: string | null;
  episode: string | null;
  at: string | null;
  site: string | null;
}

// Where a listed recipe is, after its source's name: "Claire Ptak · p. 112",
// "May 2024 · p. 42", "Season 1, episode 2, at 12:34", "example.com".
export function whereItIs(r: Listed): string {
  const parts: string[] = [];
  if (r.authors.length) parts.push(r.authors.length > 1 ? `${r.authors[0]} and others` : r.authors[0]);
  if (r.issue) parts.push(issueName(r.issue));
  if (r.episode) parts.push(r.at ? `${r.episode}, at ${r.at}` : r.episode);
  if (r.site) parts.push(r.site);
  if (r.source_kind === "packaging") parts.push("on the packaging");
  if (r.source_kind === "family") parts.push("family collection");
  const pages = [...new Set(r.pages)];
  if (pages.length) parts.push(`p. ${pages.join(" / ")}`);
  return parts.join(" · ");
}

// sort "name": A to Z, rather than most used first; top: only those that
// come under nothing.
export async function listIngredients(
  q: string,
  offset = 0,
  options: { sort?: "uses" | "name"; top?: boolean } = {},
): Promise<IngredientList> {
  const query = new URLSearchParams({ q });
  if (offset) query.set("offset", String(offset));
  if (options.sort === "name") query.set("sort", "name");
  if (options.top) query.set("top", "true");
  const res = await fetch(`/api/ingredients?${query}`);
  if (!res.ok) throw new Error("The ingredients couldn't be loaded.");
  return res.json();
}

// under: list the recipes using anything under it too.
export async function fetchIngredient(
  id: string,
  offset = 0,
  under = false,
): Promise<Ingredient | null> {
  const query = new URLSearchParams();
  if (offset) query.set("offset", String(offset));
  if (under) query.set("under", "true");
  const res = await fetch(`/api/ingredients/${id}?${query}`);
  if (res.status === 404 || res.status === 422) return null;
  if (!res.ok) throw new Error("This ingredient couldn't be loaded.");
  return res.json();
}

export interface Named {
  id: string;
  name: string;
}

// A rename onto a name another ingredient has: the page offers to merge.
export class Taken extends Error {
  constructor(
    message: string,
    readonly ingredient: Named,
  ) {
    super(message);
  }
}

async function send(path: string, method: string, body?: unknown) {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const out = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = out.detail;
    if (detail?.ingredient) throw new Taken(detail.message, detail.ingredient);
    throw new Error(typeof detail === "string" ? detail : "That didn't work. Try again.");
  }
  return out;
}

export async function renameIngredient(id: string, name: string): Promise<Named> {
  return send(`/api/ingredients/${id}`, "PATCH", { name });
}

// Resolves to the ingredient that's left.
export async function mergeIngredient(id: string, into: string): Promise<Named> {
  return send(`/api/ingredients/${id}/merge`, "POST", { into });
}

export async function deleteIngredient(id: string): Promise<void> {
  await send(`/api/ingredients/${id}`, "DELETE");
}

export async function deleteAlias(id: string, aliasId: string): Promise<void> {
  await send(`/api/ingredients/${id}/aliases/${aliasId}`, "DELETE");
}

export interface SearchResult {
  // The sources searched within, if any were.
  sources: Named[];
  ingredients: Named[];
  // Those you don't have or want: recipes needing one are left out.
  without: Named[];
  // IDs in the search that name no ingredient now, as after a merge.
  missing: string[];
  missing_sources: string[];
  // The title words searched for.
  q: string;
  // With ingredients: how many of the recipe's lines you have, of how many,
  // and the lines you don't. Null without ingredients.
  recipes: (Listed & {
    have: number | null;
    lines: number | null;
    needs: string[];
    // Which of the ingredients you have it uses, in your order.
    uses: string[];
  })[];
  total: number;
  // Recipes a page holds.
  per_page: number;
}

// Recipes ranked by how much of them the ingredients cover, narrowed by
// title words, sources and kinds of source.
export async function searchRecipes(
  ids: string[],
  {
    offset = 0,
    sources = [],
    q = "",
    kinds = [],
    without = [],
  }: {
    offset?: number;
    sources?: string[];
    q?: string;
    kinds?: string[];
    without?: string[];
  } = {},
): Promise<SearchResult> {
  const query = new URLSearchParams(ids.map((id) => ["ingredient", id]));
  if (q.trim()) query.set("q", q.trim());
  for (const source of sources) query.append("source", source);
  for (const kind of kinds) query.append("kind", kind);
  for (const id of without) query.append("without", id);
  if (offset) query.set("offset", String(offset));
  const res = await fetch(`/api/search?${query}`);
  if (!res.ok) throw new Error("The search didn't work. Try again.");
  return res.json();
}

// Puts an ingredient under another, or (parent null) under nothing.
export async function setParent(id: string, parent: string | null): Promise<void> {
  await send(`/api/ingredients/${id}/parent`, "PUT", { parent });
}
