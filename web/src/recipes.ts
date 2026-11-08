// What /api/recipes returns, and saving one.

import type { Swap } from "./substitutions";

export interface RecipePage {
  edition_id: string;
  edition_title: string | null;
  isbn13: string | null;
  published_year: number | null;
  page: string | null;
}

export interface Recipe {
  id: string;
  title: string;
  source: { id: string; title: string; kind: "book" | "website" | "magazine" | "newspaper" | "tv_show" | "podcast" | "video_channel" | "social" | "packaging" };
  pages: RecipePage[];
  // A website's recipe: the page it's on.
  web_address: string | null;
  // That page, with the Internet Archive's copy when there is one.
  // A magazine's or newspaper's recipe: its issue, at its page.
  issue: { id: string; label: string; published_on: string | null; page: string | null } | null;
  // A TV show's, podcast's or video channel's recipe: its episode, at a time.
  episode: {
    id: string;
    // How it reads: Season 2, episode 5, “Fat”.
    name: string;
    season: number | null;
    number: number | null;
    title: string | null;
    url: string | null;
    aired_on: string | null;
    // 12:34, or 1:02:03.
    at: string | null;
  } | null;
  web_page: {
    id: string;
    url: string;
    archive_url: string | null;
    archived_at: string | null;
    // Marked when the page no longer has the recipe.
    gone: boolean;
  } | null;
  // As typed, for the edit form.
  ingredients: string[];
  // The same lines read into their options, page references linked.
  lines: {
    text: string;
    options: {
      name: string;
      page: string | null;
      recipe: { id: string; title: string } | null;
      ingredient: { id: string; name: string } | null;
    }[];
  }[];
  // Recipes in the book that use this one.
  used_in: { id: string; title: string }[];
  // What can stand in for its ingredients, the recipes it cites, or itself.
  swaps: Swap[];
}

export interface RecipeIn {
  title: string;
  // Only the editions the recipe is in; page null = in it, page not recorded.
  editions: { edition_id: string; page: string | null }[];
  // A website's recipe instead: the page's address.
  web_address?: string | null;
  // A magazine's or newspaper's: the issue (its name, or its date) and page.
  issue?: string | null;
  issue_date?: string | null;
  issue_page?: string | null;
  // A show's: which episode (any of these), and the time in it.
  episode?: {
    season: number | null;
    number: number | null;
    title: string | null;
    address: string | null;
    aired_on: string | null;
    at: string | null;
  } | null;
  ingredients: string[];
}

// Adds (bookId given) or changes (recipeId given) a recipe; resolves to its
// ID, or rejects with the server's reason to show beside the form.
export async function saveRecipe(
  body: RecipeIn,
  target: { bookId: string } | { recipeId: string },
): Promise<string> {
  const isNew = "bookId" in target;
  const res = await fetch(
    isNew ? `/api/sources/${target.bookId}/recipes` : `/api/recipes/${target.recipeId}`,
    {
      method: isNew ? "POST" : "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  const out = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof out.detail === "string" ? out.detail : "That didn't save. Try again.");
  }
  return out.id;
}

export async function removeRecipe(recipeId: string): Promise<void> {
  const res = await fetch(`/api/recipes/${recipeId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("That didn't remove it. Try again.");
}

// What the entry rules say about a line: shown under the form, never enforced.
export interface LineReview {
  problems: string[];
  // The line as the rules would have it, when that's a change.
  suggestion: string | null;
  // The rules would leave the whole line out.
  remove: boolean;
}

export async function checkLines(lines: string[]): Promise<LineReview[]> {
  const res = await fetch("/api/ingredient-lines/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lines }),
  });
  if (!res.ok) throw new Error("The lines couldn't be checked.");
  return (await res.json()).lines;
}

async function webPageCall(path: string, method: string, body?: unknown) {
  const res = await fetch(`/api/web-pages/${path}`, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const out = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof out.detail === "string" ? out.detail : "That didn't work.");
  return out;
}

// Asks the Internet Archive for a copy; it arrives after a minute or two.
export async function archivePage(pageId: string): Promise<void> {
  await webPageCall(`${pageId}/archive`, "POST");
}

// Every web page without a copy yet; resolves to how many were asked for.
export async function archiveMissing(): Promise<number> {
  return (await webPageCall("archive-missing", "POST")).pages;
}

export async function markGone(pageId: string, gone: boolean): Promise<void> {
  await webPageCall(`${pageId}/gone`, "PUT", { gone });
}
