// Saved recipes (routers/saved.py): the ones you want to cook, and the ones
// you have; shared with household groups as the shelf is.
import type { Listed } from "./ingredients";

export type State = "want" | "cooked";

export interface GroupRef {
  id: string;
  name: string;
}

// A list shared with you, and whether a recipe is on it.
export interface OtherList {
  owner_id: string;
  owner_name: string | null;
  editable: boolean;
  state: State | null;
}

export interface IsSaved {
  recipe_id: string;
  // null: not saved.
  state: State | null;
  others: OtherList[];
}

export interface SavedRecipe extends Listed {
  state: State;
  saved_at: string;
}

export interface SharedList {
  owner_id: string;
  owner_name: string | null;
  // Whether you may change what's on it.
  editable: boolean;
  // The groups of yours it's shared through.
  through: GroupRef[];
  recipes: SavedRecipe[];
}

export interface Saved {
  recipes: SavedRecipe[];
  // The groups yours is shared with, and your groups to choose from.
  shared_with: GroupRef[];
  groups: GroupRef[];
  shared: SharedList[];
}

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

// Someone else's list, shared with you to change, or your own.
const whose = (owner?: string) => (owner ? `?owner=${owner}` : "");

export const mySaved = () => send<Saved>("/api/saved");
export const isSaved = (recipeId: string) => send<IsSaved>(`/api/saved/${recipeId}`);
export const save = (recipeId: string, state: State, owner?: string) =>
  send<IsSaved>(`/api/saved/${recipeId}${whose(owner)}`, "PUT", { state });
export const unsave = (recipeId: string, owner?: string) =>
  send<void>(`/api/saved/${recipeId}${whose(owner)}`, "DELETE");
export const shareSaved = (groups: string[]) =>
  send<Saved>("/api/saved/groups", "PUT", { groups });
