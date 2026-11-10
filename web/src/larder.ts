// Your larder (routers/larder.py): lists of what you have, each thing
// matched to an ingredient.

export type State = "have" | "low" | "out";

export interface Item {
  id: string;
  list_id: string;
  name: string;
  state: State;
  ingredient_id: string | null;
  ingredient: string | null;
  updated_at: string;
}

export interface List {
  id: string;
  name: string;
  position: number;
  items: Item[];
}

export interface Larder {
  lists: List[];
  counted: number;
}

async function send<T>(url: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const answer = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof answer.detail === "string" ? answer.detail : "That didn't work. Try again.");
  }
  return answer as T;
}

export const loadLarder = () => send<Larder>("/api/larder");
export const addList = (name: string) => send<List>("/api/larder/lists", "POST", { name });
export const renameList = (id: string, name: string) =>
  send<List>(`/api/larder/lists/${id}`, "PATCH", { name });
export const removeList = (id: string) => send<void>(`/api/larder/lists/${id}`, "DELETE");
export const addItem = (listId: string, name: string) =>
  send<Item>(`/api/larder/lists/${listId}/items`, "POST", { name });
export const changeItem = (
  id: string,
  change: { name?: string; state?: State; list_id?: string; ingredient_id?: string },
) => send<Item>(`/api/larder/items/${id}`, "PATCH", change);
export const removeItem = (id: string) => send<void>(`/api/larder/items/${id}`, "DELETE");

export const STATES: { state: State; label: string }[] = [
  { state: "have", label: "Have" },
  { state: "low", label: "Low" },
  { state: "out", label: "Out" },
];
