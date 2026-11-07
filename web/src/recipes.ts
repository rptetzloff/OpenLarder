// What /api/recipes returns, and saving one.

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
  book: { id: string; title: string };
  pages: RecipePage[];
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
}

export interface RecipeIn {
  title: string;
  // Only the editions the recipe is in; page null = in it, page not recorded.
  editions: { edition_id: string; page: string | null }[];
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
    isNew ? `/api/books/${target.bookId}/recipes` : `/api/recipes/${target.recipeId}`,
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
