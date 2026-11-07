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
