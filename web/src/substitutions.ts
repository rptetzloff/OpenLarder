// Substitutions and diets: what /api/substitutions and /api/diets take and return.

export interface Thing {
  kind: "ingredient" | "recipe";
  id: string;
  name: string;
}

export interface Diet {
  id: string;
  name: string;
  // The allergens it avoids (diets.py); absent where a swap names it.
  avoids: string[];
  // Those it avoids only together: Kosher's meat with milk.
  together: { allergen: string; other: string }[];
}

type Found = { key: string; label: string; status: "contains" | "may_contain" };
type Has = { ingredient: Thing; status: "contains" | "may_contain" };

// A recipe checked for a diet: its ingredients that record an allergen the
// diet avoids, with the swaps recorded for them.
export interface DietCheck {
  diet: Diet;
  lines: {
    ingredient: Thing;
    found: { key: string; label: string; status: "contains" | "may_contain" }[];
    swaps: Swap[];
  }[];
  // Two things the diet avoids together, both recorded in this recipe.
  together: { allergen: Found; other: Found; has: Has[]; has_other: Has[] }[];
  notice: string;
}

export interface Swap {
  id: string;
  instead_of: Thing;
  use: Thing;
  diet: Pick<Diet, "id" | "name"> | null;
  // null: contributed rather than printed in a book.
  source: { source_id: string; source_title: string; edition_id: string; page: string | null } | null;
  note: string | null;
}

export interface SwapIn {
  instead_of: { ingredient_id?: string; recipe_id?: string };
  use: { ingredient_id?: string; recipe_id?: string };
  diet_id: string | null;
  source_edition_id: string | null;
  source_page: string | null;
  note: string | null;
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

export function side(t: Thing) {
  return t.kind === "ingredient" ? { ingredient_id: t.id } : { recipe_id: t.id };
}

export async function listDiets(): Promise<Diet[]> {
  return send("/api/diets", "GET");
}

// The diet by this name: a new one, or the one already called that.
export async function addDiet(name: string): Promise<Diet> {
  return send("/api/diets", "POST", { name });
}

export async function setDietAllergens(id: string, allergens: string[]): Promise<Diet> {
  return send(`/api/diets/${id}/allergens`, "PUT", { allergens });
}

export async function checkDiet(recipeId: string, dietId: string): Promise<DietCheck> {
  return send(`/api/recipes/${recipeId}/diets/${dietId}`, "GET");
}

export async function addSwap(body: SwapIn): Promise<Swap> {
  return send("/api/substitutions", "POST", body);
}

export async function removeSwap(id: string): Promise<void> {
  await send(`/api/substitutions/${id}`, "DELETE");
}
