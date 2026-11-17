// Your equipment (routers/equipment_lists.py): lists of what you have and
// want, each thing matched to a piece of equipment. The larder's client
// (larder.ts) over again: Ray, 2026-11-16, "Named lists, like the larder".

// As a book on a shelf is (Ray, 2026-11-16: "Have / Want"). A larder's
// "low" and "out" have no meaning for equipment.
export type State = "have" | "want";

export interface Item {
  id: string;
  list_id: string;
  name: string;
  state: State;
  equipment_id: string | null;
  equipment: string | null;
  updated_at: string;
}

export interface GroupRef {
  id: string;
  name: string;
}

export interface List {
  id: string;
  name: string;
  position: number;
  items: Item[];
  // Yours, or shared with you by its owner.
  mine: boolean;
  owner_name: string | null;
  // Whether you may change what's on it.
  editable: boolean;
  // The groups it's shared with: all for its owner, yours otherwise.
  shared_with: GroupRef[];
}

export interface Lists {
  lists: List[];
  // Things that count as had: have, and matched.
  counted: number;
  // Your groups, to share a list with.
  groups: GroupRef[];
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

const API = "/api/equipment-lists";
export const loadLists = () => send<Lists>(API);
export const addList = (name: string) => send<List>(`${API}/lists`, "POST", { name });
export const renameList = (id: string, name: string) =>
  send<List>(`${API}/lists/${id}`, "PATCH", { name });
export const removeList = (id: string) => send<void>(`${API}/lists/${id}`, "DELETE");
export const addItem = (listId: string, name: string) =>
  send<Item>(`${API}/lists/${listId}/items`, "POST", { name });
export const changeItem = (
  id: string,
  change: { name?: string; state?: State; list_id?: string; equipment_id?: string },
) => send<Item>(`${API}/items/${id}`, "PATCH", change);
export const removeItem = (id: string) => send<void>(`${API}/items/${id}`, "DELETE");
export const shareList = (id: string, groups: string[]) =>
  send<List>(`${API}/lists/${id}/groups`, "PUT", { groups });

export const STATES: { state: State; label: string }[] = [
  { state: "have", label: "Have" },
  { state: "want", label: "Want" },
];
