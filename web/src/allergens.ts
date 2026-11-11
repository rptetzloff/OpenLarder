// Allergens on ingredients (allergens.py): crowdsourced, shown with the
// notice wherever they are, and never as a recipe being safe for anyone
// (SCOPING.md, Allergen data).

import { ref } from "vue";

export type Status = "contains" | "may_contain" | "free";

export interface Allergen {
  key: string;
  label: string;
}

// What an ingredient records, or inherits from a broader one.
export interface IngredientAllergen extends Allergen {
  status: Status;
  inherited: boolean;
  // Which broader one, if you may see it.
  inherited_from: { id: string; name: string } | null;
}

// What a recipe's ingredients contain or may contain.
export interface RecipeAllergen extends Allergen {
  status: "contains" | "may_contain";
  ingredients: { id: string; name: string; status: "contains" | "may_contain" }[];
}

export const STATUS_WORDS: Record<Status, string> = {
  contains: "Contains",
  may_contain: "May contain",
  free: "Doesn't contain",
};

export const list = ref<Allergen[] | null>(null);
export const notice = ref("");
let asked: Promise<void> | null = null;
export function loadAllergens(): Promise<void> {
  asked ??= fetch("/api/allergens")
    .then((r) => (r.ok ? r.json() : { allergens: [], notice: "" }))
    .then((got: { allergens: Allergen[]; notice: string }) => {
      list.value = got.allergens;
      notice.value = got.notice;
    })
    .catch(() => {
      list.value = [];
    });
  return asked;
}

export async function setAllergens(
  ingredientId: string,
  statuses: Record<string, Status>,
): Promise<IngredientAllergen[]> {
  const res = await fetch(`/api/ingredients/${ingredientId}/allergens`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ statuses }),
  });
  const out = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof out.detail === "string" ? out.detail : "That didn't save. Try again.");
  }
  return out;
}
