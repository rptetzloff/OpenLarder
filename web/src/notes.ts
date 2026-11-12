// Notes on recipes (routers/notes.py): your own words about one, yours
// alone unless you tick which of your groups see it.
import type { Listed } from "./ingredients";

export interface GroupRef {
  id: string;
  name: string;
}

export interface Notes {
  mine: { body: string; shared_with: GroupRef[]; updated_at: string } | null;
  // Your groups, to share a note with.
  groups: GroupRef[];
  // Other people's notes on this recipe, shared with you.
  others: { author: string | null; body: string; through: GroupRef[]; updated_at: string }[];
}

// A recipe with a note you can see.
export interface NotedRecipe extends Listed {
  body: string;
  mine: boolean;
  author: string | null;
  noted_at: string;
}

export const MAX_NOTE = 2000;

async function send<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const failed = await res.json().catch(() => ({}));
    throw new Error(
      typeof failed.detail === "string" ? failed.detail : "That didn't work. Try again.",
    );
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const recipeNotes = (recipeId: string) => send<Notes>(`/api/recipes/${recipeId}/notes`);
export const writeNote = (recipeId: string, body: string, groups: string[]) =>
  send<Notes>(`/api/recipes/${recipeId}/notes`, "PUT", { body, groups });
export const removeNote = (recipeId: string) =>
  send<void>(`/api/recipes/${recipeId}/notes`, "DELETE");
export const allNotes = async () => (await send<{ notes: NotedRecipe[] }>("/api/notes")).notes;
