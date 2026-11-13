// Household groups: private family collections shared with family
// (routers/groups.py).

export type Role = "view" | "edit" | "admin";

// What each role may do, as the pages say it.
export const ROLE_NAMES: Record<Role, string> = {
  view: "Can view",
  edit: "Can add and change recipes",
  admin: "Admin: also manages the group",
};

export interface GroupSummary {
  id: string;
  name: string;
  // Your role in it.
  role: Role;
  members: number;
}

export interface Group {
  id: string;
  name: string;
  role: Role;
  members: { user_id: string; name: string | null; role: Role }[];
  // Waiting to be used; shown to the group's admins only.
  invites: { id: string; role: Role; expires_at: string }[];
  collections: { id: string; title: string; owner_name: string | null }[];
}

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "That didn't work.");
  return data as T;
}

export const listGroups = () => send<GroupSummary[]>("/api/groups", "GET");
export const makeGroup = (name: string) => send<GroupSummary>("/api/groups", "POST", { name });
export const getGroup = (id: string) => send<Group>(`/api/groups/${id}`, "GET");
export const renameGroup = (id: string, name: string) =>
  send<GroupSummary>(`/api/groups/${id}`, "PATCH", { name });
export const deleteGroup = (id: string) => send<void>(`/api/groups/${id}`, "DELETE");
// The token is in this answer only; the link is /invite/<token>.
export const makeInvite = (id: string, role: Role) =>
  send<{ id: string; role: Role; expires_at: string; token: string }>(
    `/api/groups/${id}/invites`,
    "POST",
    { role },
  );
export const cancelInvite = (id: string, invite: string) =>
  send<void>(`/api/groups/${id}/invites/${invite}`, "DELETE");
export const setRole = (id: string, user: string, role: Role) =>
  send<unknown>(`/api/groups/${id}/members/${user}`, "PUT", { role });
// Leave (your own ID), or as its admin remove someone.
export const removeMember = (id: string, user: string) =>
  send<void>(`/api/groups/${id}/members/${user}`, "DELETE");
export const readInvite = (code: string) =>
  send<{ group: string; role: Role }>(`/api/invites/${encodeURIComponent(code)}`, "GET");
export const acceptInvite = (code: string) =>
  send<GroupSummary>(`/api/invites/${encodeURIComponent(code)}/accept`, "POST");
// Which of your groups see a family collection of yours: all of them, listed.
export const shareCollection = (source: string, groups: string[]) =>
  send<{ id: string; name: string }[]>(`/api/sources/${source}/groups`, "PUT", { groups });
