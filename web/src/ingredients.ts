// Canonical ingredients: what /api/ingredients returns.

export interface IngredientSummary {
  id: string;
  name: string;
  recipes: number;
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
  recipes: { id: string; title: string; book_id: string; book_title: string; pages: string[] }[];
  total: number;
}

export async function listIngredients(q: string, offset = 0): Promise<IngredientList> {
  const query = new URLSearchParams({ q });
  if (offset) query.set("offset", String(offset));
  const res = await fetch(`/api/ingredients?${query}`);
  if (!res.ok) throw new Error("The ingredients couldn't be loaded.");
  return res.json();
}

export async function fetchIngredient(id: string, offset = 0): Promise<Ingredient | null> {
  const res = await fetch(`/api/ingredients/${id}${offset ? `?offset=${offset}` : ""}`);
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
